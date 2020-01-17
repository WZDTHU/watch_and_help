import numpy as np
from pathlib import Path
import random
import time
import math
import copy
import importlib
import multiprocessing
import ipdb


from vh_graph.envs import belief as Belief
from vh_graph.envs.vh_env import VhGraphEnv

from MCTS import *

def find_heuristic(env_graph, observations, object_target):
    target = int(object_target.split('_')[-1])
    observation_ids = [x['id'] for x in observations['nodes']]


    while target not in observation_ids:
        containers = [e['to_id'] for e in env_graph['edges']
                      if e['from_id'] == target and e['relation_type'] == 'INSIDE']
        target = containers[0]

    target_node = [node for node in observations['nodes'] if node['id'] == target][0]

    return [target_node], [['walk', 'open']]


def get_plan(sample_id, root_action, root_node, env, mcts, nb_steps, goal_ids, res):
    init_vh_state = env.vh_state
    init_state = env.state
    observations = env.get_observations(char_index=0)
    # print('init state:', init_state)

    q = goal_ids

    l = 0


    import time
    t1 = time.time()




    
    if env.is_terminal(0, init_state):
        terminal = True
        res[sample_id] = None
        return
    # if root_action is None:
    root_node = Node(id={root_action: [init_vh_state, init_state, goal_ids]},
                     num_visited=0,
                     sum_value=0,
                     is_expanded=False)
    curr_node = root_node
    next_root, plan = mcts.run(curr_node,
                               nb_steps,
                               find_heuristic)
    print('TS', time.time() - t1)
    print('init state:', [e for e in init_state['edges'] if e['from_id'] == 162])
    print('plan:', plan)
    # else:
    #     action, _, next_root = mcts.select_next_root(root_node)
    print(root_node.sum_value)
    # print(sample_id, res[sample_id])
    if sample_id is not None:
        res[sample_id] = plan
    else:
        return plan, next_root


class MCTS_agent:
    """
    MCTS for a single agent
    """
    def __init__(self, env, max_episode_length, num_simulation, max_rollout_steps, c_init, c_base, num_samples=1, num_processes=1, comm=None):
        self.env = env
        self.sim_env = VhGraphEnv()
        self.sim_env.pomdp = True
        self.belief = None
        self.max_episode_length = max_episode_length
        self.num_simulation = num_simulation
        self.max_rollout_steps = max_rollout_steps
        self.c_init = c_init
        self.c_base = c_base
        self.num_samples = num_samples
        self.num_processes = num_processes
        self.previous_belief_graph = None

        # Indicates whether there is a unity simulation
        self.comm = comm


    def sample_belief(self, obs_graph):
        self.belief.update_from_gt_graph(obs_graph)
        if self.previous_belief_graph is None:
            self.belief.reset_belief()
            new_graph = self.belief.sample_from_belief()
            new_graph = self.belief.update_graph_from_gt_graph(obs_graph)
            self.previous_belief_graph = new_graph
        else:
            new_graph = self.belief.update_graph_from_gt_graph(obs_graph)
            self.previous_belief_graph = new_graph


    def get_action(self, graph, task_goal):
        first_time = time.time()
        self.mcts = MCTS(self.sim_env, self.max_episode_length, self.num_simulation, self.max_rollout_steps,
                         self.c_init, self.c_base)
        if self.mcts is None:
            raise Exception

        # TODO: is this correct?
        nb_steps = 0
        root_action = None
        root_node = None



        plan, root_node = get_plan(None, root_action, root_node, self.sim_env, self.mcts, nb_steps, task_goal, None)

        action = plan[0]
        info = {
            'plan': plan,
            'action': action,
            'belief': copy.deepcopy(self.belief.edge_belief),
            'belief_graph': copy.deepcopy(self.sim_env.vh_state.to_dict())
        }
        return action, info

    def reset(self, graph, task_goal):
        if self.comm is not None:
            s, graph = self.comm.environment_graph()


        self.env.reset(graph, task_goal)
        self.env.to_pomdp()
        gt_state = self.env.vh_state.to_dict()
        self.belief = Belief.Belief(gt_state)
        self.sample_belief(self.env.get_observations(char_index=0))
        self.sim_env.reset(self.previous_belief_graph, task_goal)
        self.sim_env.to_pomdp()



    def rollout(self, graph, task_goal):

        self.reset(graph, task_goal)
        nb_steps = 0
        done = False

        root_action = None
        root_node = None
        # print(self.sim_env.pomdp)


        history = {'belief': [], 'plan': [], 'action': [], 'belief_graph': []}
        while not done and nb_steps < self.max_episode_length:
            if nb_steps < 0:
                # Debug
                action = gt_actions[nb_steps]
                plan = [action]
                belief_graph, belief = None, None

            else:
                action, info = self.get_action(graph, task_goal[0])
                plan, belief, belief_graph = info['plan'], info['belief'], info['belief_graph']



            history['belief'].append(belief)
            history['plan'].append(plan)
            history['action'].append(action)
            history['belief_graph'].append(belief_graph)

            reward, state, infos = self.env.step({0: action})
            done = abs(reward[0] - 1.0) < 1e-6
            _, _, _ = self.sim_env.step({0: action})
            nb_steps += 1


            print(nb_steps, action, reward, plan)
            obs_graph = self.env.get_observations(char_index=0)
            self.sample_belief(self.env.get_observations(char_index=0))
            self.sim_env.reset(self.previous_belief_graph, task_goal)


            state = self.env.vh_state.to_dict()

            # # if action == plan[-1]:
            # obs_graph = self.env.get_observations(0)
            # self.sample_belief(self.env.get_observations(0))
            # # self.sim_env.reset_graph(self.previous_belief_graph)
            # self.sim_env.reset(self.previous_belief_graph, task_goal)
            # # # new_graph = self.bel.update_graph_from_gt_graph(obs_graph)
            # # self.bel.update_from_gt_graph(obs_graph)
            # # new_graph = self.bel.sample_from_belief()
            # # self.sim_env.reset(new_graph, task_goal)
            sim_state = self.sim_env.vh_state.to_dict()
            self.sim_env.to_pomdp()
            # self.sim_env.vh_state._script_objects = dict(self.env.vh_state._script_objects)
            # print('sim')
            #id_goal = 2038
            # id_agent = 162
            # print([n for n in sim_state['nodes'] if n['category'] == 'Rooms'])
            # print([n for n in sim_state['nodes'] if n['id'] == id_goal])
            # print([[(n['id'], n['class_name']) for n in sim_state['nodes'] if n['id'] == e['from_id']] for e in sim_state['edges'] if 41 in e.values()])
            # print('real state:', [e for e in state['edges'] if goal_id in e.values()])
            # print('real state:', [e for e in state['edges'] if id_agent in e.values()])
            #
            # print('sim state:', [e for e in sim_state['edges'] if goal_id in e.values()])# and e['relation_type'] == 'INSIDE'])
            # print('sim state:', [e for e in sim_state['edges'] if e['from_id'] == 229])
            # # print([e for e in sim_state['edges'] if 117 in e.values() and e['relation_type'] == 'INSIDE'])
            # print('sim state:', [e for e in sim_state['edges'] if id_agent in e.values()])
            #input('press any key to continue...')

        import pdb
        return history

