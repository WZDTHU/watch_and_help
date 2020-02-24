import pickle
import pdb
import sys
import os
import random
import json
import numpy as np
import copy

random.seed(10)

home_path = '../../'
sys.path.append(home_path+'/vh_mdp')
sys.path.append(home_path+'/virtualhome')

from simulation.unity_simulator import comm_unity as comm_unity
from simulation.evolving_graph.utils import load_graph_dict
from profilehooks import profile


class SetInitialGoal:
    def __init__(self, obj_position, class_name_size, init_pool_tasks, task_name, same_room=True):
        self.task_name = task_name
        self.init_pool_tasks = init_pool_tasks
        self.obj_position = obj_position
        self.class_name_size = class_name_size
        self.object_id_count = 1000
        self.surface_size = {}
        self.surface_used_size = {}
        self.max_num_place = 50

        self.min_num_other_object = 0#15
        self.max_num_other_object = 0#45
        
        self.add_goal_obj_success = True
        self.set_goal()

        self.same_room = same_room

    def set_goal(self):
        
        if self.task_name in ['setup_table', 'clean_table', 'put_dishwasher', 'unload_dishwasher', 'put_fridge', 'read_book', 'prepare_food', 'watch_tv']:
            self.init_pool = self.init_pool_tasks[self.task_name]
        
        elif self.task_name=='setup_table_prepare_food':
            self.init_pool = self.init_pool_tasks["setup_table"]
            self.init_pool.update(self.init_pool_tasks["prepare_food"])

        elif self.task_name=='setup_table_read_book':
            self.init_pool = self.init_pool_tasks["setup_table"]
            self.init_pool.update(self.init_pool_tasks["read_book"])
        
        elif self.task_name=='setup_table_watch_tv':
            self.init_pool = self.init_pool_tasks["setup_table"]
            self.init_pool.update(self.init_pool_tasks["watch_tv"])

        elif self.task_name=='setup_table_put_fridge':
            self.init_pool = self.init_pool_tasks["setup_table"]
            self.init_pool.update(self.init_pool_tasks["put_fridge"])

        elif self.task_name=='setup_table_put_dishwasher':
            self.init_pool = self.init_pool_tasks["setup_table"]
            self.init_pool.update(self.init_pool_tasks["put_dishwasher"])

        
        ## make sure the goal is not empty
        while 1:
            self.goal = {}
            for k,v in self.init_pool.items():
                self.goal[k] = random.randint(v['min_num'], v['max_num'])
            
            count = 0
            for k,v in self.goal.items(): 
                count+=v

            if (self.task_name=='read_book' or self.task_name=='watch_tv') and (count!=0):
                break

            if 2<=count<=6:
                break
            
        ## example setup table
        # task_name = 'setup_table'
        # goal = {'plate': 2,
        #         'glasses': 2,
        #         'wineglass': 1,
        #         'cutleryfork': 0}

    def get_obj_room(self, obj_id):
        room_ids = [node['id'] for node in graph['nodes'] if node['category'] == 'Rooms']
        # room_info = {edge['from_id']: edge['to_id'] for edge in graph['edges'] if edge['to_id'] in room_ids and edge['relation_type'] == 'INSIDE'}
        room_info = [edge['to_id'] for edge in graph['edges'] if edge['to_id'] in room_ids and edge['relation_type'] == 'INSIDE' and edge['from_id']==obj_id]
        assert len(room_info)==1

        objs_in_room = [edge['from_id'] for edge in graph['edges'] if edge['to_id']==room_info[0] and edge['relation_type'] == 'INSIDE']

        return objs_in_room


    def check_goal_achievable(self, graph, comm, env_goal):
        graph_copy = copy.deepcopy(graph)
        if (self.task_name == 'setup_table') or (self.task_name == 'put_dishwasher') or (self.task_name == 'put_fridge') or (self.task_name == 'prepare_food'):
            for goal in env_goal[self.task_name]:
                # print(self.object_id_count)
                subgoal_name = list(goal.keys())[0]
                num_obj = list(goal.values())[0]
                obj = subgoal_name.split('_')[1]
                target_id = int(subgoal_name.split('_')[3])

                if self.same_room:
                    objs_in_room = self.get_obj_room(target_id)
                else:
                    objs_in_room = None

                old_nodes = [node for node in graph_copy['nodes'] if obj == node['class_name']]
                obj_ids = [node['id'] for node in graph_copy['nodes'] if obj == node['class_name']]
                graph_copy = self.remove_obj(graph_copy, obj_ids)

                self.object_id_count, graph, _ = self.add_obj(graph_copy, obj, num_obj, self.object_id_count, old_nodes=old_nodes, objs_in_room=objs_in_room, only_position=target_id)
            success, message = comm.expand_scene(graph_copy)
        else:
            success = 1
            message = self.task_name

        print(success, message)
        return success


    def convert_size(self, envsize):
        size = envsize[0]*envsize[2]
        return size


    def check_placeable(self, graph, surface_id, obj_name):
        obj_size = self.convert_size(self.class_name_size[obj_name])

        surface_node = [node for node in graph['nodes'] if node['id']==surface_id]
        if surface_id not in self.surface_size:
            surface_node = [node for node in graph['nodes'] if node['id']==surface_id]
            assert len(surface_node)
            self.surface_size[surface_id] = self.convert_size(self.class_name_size[surface_node[0]['class_name']])
        

        if surface_id not in self.surface_used_size:
            objs_on_surface = [edge['from_id'] for edge in graph['edges'] if edge['to_id']==surface_id]
            objs_on_surface_node = [node for node in graph['nodes'] if node['id'] in objs_on_surface]
            objs_on_surface_size = [self.convert_size(self.class_name_size[node['class_name']]) for node in objs_on_surface_node]
            self.surface_used_size[surface_id] = np.sum(objs_on_surface_size) # get size from the initial graph
            

        # print(self.surface_size[surface_id])
        # print(self.surface_used_size[surface_id], obj_size, self.surface_used_size[surface_id]+obj_size)
        # print(obj_name, surface_node[0]['class_name'])


        if self.surface_size[surface_id]/2 > self.surface_used_size[surface_id]+obj_size:
            self.surface_used_size[surface_id] += obj_size
            # print('1')
            return 1
        else:
            # print('0')
            return 0


    def remove_obj(self, graph, obj_ids):
        graph['nodes'] = [node for node in graph['nodes'] if node['id'] not in obj_ids]
        graph['edges'] = [edge for edge in graph['edges'] if edge['from_id'] not in obj_ids and edge['to_id'] not in obj_ids]
        return graph


    def add_obj(self, graph, obj_name, num_obj, object_id, old_nodes, objs_in_room=None, only_position=None, except_position=None, goal_obj=False):
        
        if isinstance(except_position, int):
            except_position = [except_position]
        if isinstance(only_position, int):
            only_position = [only_position]

        edges = []
        nodes = []
        ids_class = {}
        for node in graph['nodes']:
            class_name = node['class_name']
            if class_name not in ids_class: 
                ids_class[class_name] = []
            ids_class[class_name].append(node['id'])
                                
    
        # candidates = [(obj_rel_name[0], obj_rel_name[1]) for obj_rel_name in obj_position_pool[obj_name] if obj_rel_name[1] in ids_class.keys() and (except_position is None or obj_rel_name[1] not in except_position) and (only_position is None or obj_rel_name[1] in only_position)]


        candidates = [(obj_rel_name[0], obj_rel_name[1]) for obj_rel_name in self.obj_position[obj_name] if obj_rel_name[1] in ids_class.keys()]

        id2node = {node['id']: node for node in graph['nodes']}
        success_add = 0
        locations = []
        for i in range(num_obj):
            # TODO: we need to check the properties and states, probably the easiest is to get them from the original set of graphs

            num_place = 0
            
            while 1:
                if num_place > self.max_num_place:
                    break

                if only_position!=None:
                    num_place2 = 0
                    while 1:
                        if num_place2 > self.max_num_place:
                            break
                        target_id = random.choice(only_position)
                        if self.same_room and goal_obj:
                            if target_id in objs_in_room:
                                break
                            else:
                                num_place2 += 1
                        else:
                            break

                    # target_id = random.choice(only_position)
                    
                    target_pool = [k for k,v in ids_class.items() if target_id in v]
                    target_position_pool = [tem[0] for tem in self.obj_position[obj_name] if tem[1] in target_pool]
                    
                    if len(target_pool)==0 or len(target_position_pool)==0 or (num_place2>self.max_num_place):
                        num_place += 1
                        continue
                    else:
                        relation = random.choice(target_position_pool)
                        


                else:
                    num_place2 = 0
                    while 1:
                        if num_place2 > self.max_num_place:
                            break

                        relation, target_classname = random.choice(candidates)
                        target_id = random.choice(ids_class[target_classname])

                        if self.same_room and goal_obj:
                            if target_id in objs_in_room:
                                break
                            else:
                                num_place2 += 1
                        else:
                            break

                    # for tem in candidates:
                    #     if 'plate' in tem:
                    #         print(candidates)
                    #         pdb.set_trace()


                    ## target in except_position
                    if ((except_position!=None) and (target_id in except_position)) or (num_place2>self.max_num_place):
                        num_place += 1
                        continue
                    
                    

                ## check if it is possible to put object in this surface
                placeable = self.check_placeable(graph, target_id, obj_name)

                print(obj_name, id2node[target_id]['class_name'], placeable)
                # print('placing %s: %dth (total %d), success: %d' % (obj_name, i+1, num_obj, placeable))
                



                if placeable:
                    if i >= len(old_nodes):
                        new_node = {'id': object_id, 'class_name': obj_name, 'properties': ['GRABBABLE'], 'states': [], 'category': 'added_object'}
                        nodes.append(new_node)
                        edges.append({'from_id': object_id, 'relation_type': relation, 'to_id': target_id})
                        object_id += 1
                    else:
                        new_node = old_nodes[i]
                        nodes.append(new_node)
                        edges.append({'from_id': old_nodes[i]['id'], 'relation_type': relation, 'to_id': target_id})
                    success_add += 1
                    locations.append(target_id)
                    break
                else:
                    num_place += 1

                
        
        graph['nodes'] += nodes
        graph['edges'] += edges

        if goal_obj:
            if success_add!=num_obj:
                self.add_goal_obj_success = False

        return object_id, graph, locations




    def setup_other_objs(self, graph, object_id, objs_in_room=None, except_position=None):
        new_object_pool = [tem for tem in self.obj_position.keys() if tem not in list(self.goal.keys())] # remove objects in goal

        self.num_other_obj = random.choice(list(range(self.min_num_other_object, self.max_num_other_object+1)))
        for i in range(self.num_other_obj):    
            obj_name = random.choice(new_object_pool)
            obj_in_graph = [node for node in graph['nodes'] if node['class_name']==obj_name] # if the object already in env, skip
            object_id, graph = self.add_obj(graph, obj_name, 1, object_id, objs_in_room=objs_in_room, only_position=None, except_position=except_position)

        return object_id, graph



    def set_tv_off(self, graph, tv_id):
        node = [n for n in graph['nodes'] if n['id'] == tv_id]
        assert len(node)==1
        node[0]['states'] = ['OFF']
         # + [state for state in node[0]['states'] if state not in ['ON', 'OFF']]
        return graph






    def setup_table(self, graph0, start=True):
        ## setup table
        # max_num_table = 4
        # num_table = random.randint(1, max_num_table)

        # table_ids = [node['id'] for node in graph['nodes'] if 'table' in node['class_name']]
        # self.remove_obj(graph, table_ids)
        # table_position_pool = self.obj_position['table']
        # self.add_obj(graph, 'table', num_table, table_position_pool)

        # table_ids = [node['id'] for node in graph['nodes'] if ('coffeetable' in node['class_name']) or ('kitchentable' in node['class_name'])]
        
        graph = copy.deepcopy(graph0)

        table_ids = [node['id'] for node in graph['nodes'] if ('kitchentable' in node['class_name'])]
        table_id = random.choice(table_ids)

        ## remove objects on table
        objs_on_table = [edge['from_id'] for edge in graph['edges'] if (edge['to_id']==table_id) and (edge['relation_type']=='ON')]
        graph = self.remove_obj(graph, objs_on_table)

        # tem = [node for node in graph['nodes'] if node['id']==table_id]
        # pdb.set_trace()

        if self.same_room:
            objs_in_room = self.get_obj_room(table_id)
        else:
            objs_in_room = None
        

        except_position_ids = [node['id'] for node in graph['nodes'] if ('floor' in node['class_name'])]
        except_position_ids.append(table_id)
        locations = {}

        for k,v in self.goal.items():
            old_nodes = [node for node in graph['nodes'] if k in node['class_name']]
            obj_ids = [node['id'] for node in graph['nodes'] if k in node['class_name']]
            graph = self.remove_obj(graph, obj_ids)

            num_obj = random.randint(v, self.init_pool[k]['env_max_num']+1) # random select objects >= goal
            self.object_id_count, graph, locations[k] = self.add_obj(graph, k, num_obj, self.object_id_count, old_nodes, objs_in_room=objs_in_room, except_position=except_position_ids, goal_obj=True)

        if start:
            self.object_id_count, graph = self.setup_other_objs(graph, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids)

        # new_graph = copy.deepcopy(graph)
        # new_graph['edges'] = [edge for edge in new_graph['edges'] if edge['relation_type'] == 'CLOSE']
        # for k in self.goal:
        #     if 

        ## get goal
        env_goal = {'setup_table': []}
        for k,v in self.goal.items():
            env_goal['setup_table'].append( {'put_{}_on_{}'.format(k, table_id): v} )


        return graph, env_goal






    def clean_table(self, graph, start=True):
        ## clean table
        # max_num_table = 4
        # num_table = random.randint(1, max_num_table)

        # table_ids = [node['id'] for node in graph['nodes'] if 'table' in node['class_name']]
        # self.remove_obj(graph, table_ids)
        # table_position_pool = self.obj_position['table']
        # self.add_obj(graph, 'table', num_table, table_position_pool)
        

        # table_ids = [node['id'] for node in graph['nodes'] if ('coffeetable' in node['class_name']) or ('kitchentable' in node['class_name'])]
        table_ids = [node['id'] for node in graph['nodes'] if ('kitchentable' in node['class_name'])]
        table_id = random.choice(table_ids)

        ## remove objects on table
        objs_on_table = [edge['from_id'] for edge in graph['edges'] if (edge['to_id']==table_id) and (edge['relation_type']=='ON')]
        graph = self.remove_obj(graph, objs_on_table)


        if self.same_room:
            objs_in_room = self.get_obj_room(table_id)
        else:
            objs_in_room = None
        

        except_position_ids = [node['id'] for node in graph['nodes'] if ('floor' in node['class_name'])]
        except_position_ids.append(table_id)

        for k,v in self.goal.items():
            obj_ids = [node['id'] for node in graph['nodes'] if k in node['class_name']]
            graph = self.remove_obj(graph, obj_ids)

            num_obj = random.randint(v, self.init_pool[k]['env_max_num']+1) # random select objects >= goal
            self.object_id_count, graph = self.add_obj(graph, k, v, self.object_id_count, objs_in_room=objs_in_room, only_position=table_id, goal_obj=True) ## add the first v objects on this table
            self.object_id_count, graph = self.add_obj(graph, k, num_obj-v, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids) ## add the rest objects on other places
        
        if start:
            self.object_id_count, graph = self.setup_other_objs(graph, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids)


        ## get goal
        env_goal = {'clean_table': []}
        for k,v in self.goal.items():
            env_goal['clean_table'].append( {'take_{}_off_{}'.format(k, table_id): v} )
        return graph, env_goal


    def put_dishwasher(self, graph, start=True):
        ## setup dishwasher
        # max_num_dishwasher = 4
        # num_dishwasher = random.randint(1, max_num_dishwasher)

        # dishwasher_ids = [node['id'] for node in graph['nodes'] if 'dishwasher' in node['class_name']]
        # self.remove_obj(graph, dishwasher_ids)
        # dishwasher_position_pool = self.obj_position['dishwasher']
        # self.add_obj(graph, 'dishwasher', num_dishwasher, dishwasher_position_pool)
        

        dishwasher_ids = [node['id'] for node in graph['nodes'] if 'dishwasher' in node['class_name']]
        dishwasher_id = random.choice(dishwasher_ids)

        ## remove objects in dishwasher
        objs_in_dishwasher = [edge['from_id'] for edge in graph['edges'] if (edge['to_id']==dishwasher_id) and (edge['relation_type']=='INSIDE')]
        graph = self.remove_obj(graph, objs_in_dishwasher)


        if self.same_room:
            objs_in_room = self.get_obj_room(dishwasher_id)
        else:
            objs_in_room = None
        

        except_position_ids = [node['id'] for node in graph['nodes'] if ('floor' in node['class_name'])]
        except_position_ids.append(dishwasher_id)

        for k,v in self.goal.items():
            obj_ids = [node['id'] for node in graph['nodes'] if k in node['class_name']]
            graph = self.remove_obj(graph, obj_ids)

            num_obj = random.randint(v, self.init_pool[k]['env_max_num']+1) # random select objects >= goal
            self.object_id_count, graph = self.add_obj(graph, k, num_obj, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids, goal_obj=True)
        
        if start:
            self.object_id_count, graph = self.setup_other_objs(graph, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids)


        ## get goal
        env_goal = {'put_dishwasher': []}
        for k,v in self.goal.items():
            env_goal['put_dishwasher'].append( {'put_{}_inside_{}'.format(k, dishwasher_id): v} )
        return graph, env_goal






    def unload_dishwasher(self, graph, start=True):
        ## setup dishwasher
        # max_num_dishwasher = 4
        # num_dishwasher = random.randint(1, max_num_dishwasher)

        # dishwasher_ids = [node['id'] for node in graph['nodes'] if 'dishwasher' in node['class_name']]
        # self.remove_obj(graph, dishwasher_ids)
        # dishwasher_position_pool = self.obj_position['dishwasher']
        # self.add_obj(graph, 'dishwasher', num_dishwasher, dishwasher_position_pool)
        

        dishwasher_ids = [node['id'] for node in graph['nodes'] if 'dishwasher' in node['class_name']]
        dishwasher_id = random.choice(dishwasher_ids)

        ## remove objects in dishwasher
        objs_in_dishwasher = [edge['from_id'] for edge in graph['edges'] if (edge['to_id']==dishwasher_id) and (edge['relation_type']=='INSIDE')]
        graph = self.remove_obj(graph, objs_in_dishwasher)

        if self.same_room:
            objs_in_room = self.get_obj_room(dishwasher_id)
        else:
            objs_in_room = None
        
        except_position_ids = [node['id'] for node in graph['nodes'] if ('floor' in node['class_name'])]
        except_position_ids.append(dishwasher_id)

        for k,v in self.goal.items():
            obj_ids = [node['id'] for node in graph['nodes'] if k in node['class_name']]
            graph = self.remove_obj(graph, obj_ids)

            num_obj = random.randint(v, self.init_pool[k]['env_max_num']+1) # random select objects >= goal
            self.object_id_count, graph = self.add_obj(graph, k, v, self.object_id_count, objs_in_room=objs_in_room, only_position=dishwasher_id, goal_obj=True) ## add the first v objects on this table
            self.object_id_count, graph = self.add_obj(graph, k, num_obj-v, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids) ## add the rest objects on other places
        
        if start:
            self.object_id_count, graph = self.setup_other_objs(graph, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids)


        ## get goal
        env_goal = {'unload_dishwasher': []}
        for k,v in self.goal.items():
            env_goal['unload_dishwasher'].append( {'take_{}_from_{}'.format(k, dishwasher_id): v} )
        return graph, env_goal



    def put_fridge(self, graph, start=True):
        ## setup fridge
        # max_num_fridge = 4
        # num_fridge = random.randint(1, max_num_fridge)

        # fridge_ids = [node['id'] for node in graph['nodes'] if 'fridge' in node['class_name']]
        # self.remove_obj(graph, fridge_ids)
        # fridge_position_pool = self.obj_position['fridge']
        # self.add_obj(graph, 'fridge', num_fridge, fridge_position_pool)
        

        fridge_ids = [node['id'] for node in graph['nodes'] if 'fridge' in node['class_name']]
        fridge_id = random.choice(fridge_ids)

        ## remove objects in fridge
        objs_in_fridge = [edge['from_id'] for edge in graph['edges'] if (edge['to_id']==fridge_id) and (edge['relation_type']=='INSIDE')]
        graph = self.remove_obj(graph, objs_in_fridge)

        if self.same_room:
            objs_in_room = self.get_obj_room(fridge_id)
        else:
            objs_in_room = None
        
        except_position_ids = [node['id'] for node in graph['nodes'] if ('floor' in node['class_name'])]
        except_position_ids.append(fridge_id)

        for k,v in self.goal.items():
            obj_ids = [node['id'] for node in graph['nodes'] if k in node['class_name']]
            graph = self.remove_obj(graph, obj_ids)

            num_obj = random.randint(v, self.init_pool[k]['env_max_num']+1) # random select objects >= goal
            self.object_id_count, graph = self.add_obj(graph, k, num_obj, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids, goal_obj=True)
        
        if start:
            self.object_id_count, graph = self.setup_other_objs(graph, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids)


        ## get goal
        env_goal = {'put_fridge': []}
        for k,v in self.goal.items():
            env_goal['put_fridge'].append( {'put_{}_inside_{}'.format(k, fridge_id): v} )
        return graph, env_goal




    def prepare_food(self, graph, start=True):
        # max_num_table = 4
        # num_table = random.randint(1, max_num_table)

        # table_ids = [node['id'] for node in graph['nodes'] if 'table' in node['class_name']]
        # self.remove_obj(graph, table_ids)
        # table_position_pool = self.obj_position['table']
        # self.add_obj(graph, 'table', num_table, table_position_pool)
        

        # table_ids = [node['id'] for node in graph['nodes'] if ('coffeetable' in node['class_name']) or ('kitchentable' in node['class_name'])]
        table_ids = [node['id'] for node in graph['nodes'] if ('kitchentable' in node['class_name'])]
        table_id = random.choice(table_ids)

        ## remove objects on table
        objs_on_table = [edge['from_id'] for edge in graph['edges'] if (edge['to_id']==table_id) and (edge['relation_type']=='ON')]
        graph = self.remove_obj(graph, objs_on_table)

        if self.same_room:
            objs_in_room = self.get_obj_room(table_id)
        else:
            objs_in_room = None
        
        except_position_ids = [node['id'] for node in graph['nodes'] if ('floor' in node['class_name'])]
        except_position_ids.append(table_id)

        for k,v in self.goal.items():
            obj_ids = [node['id'] for node in graph['nodes'] if k in node['class_name']]
            graph = self.remove_obj(graph, obj_ids)

            num_obj = random.randint(v, self.init_pool[k]['env_max_num']+1) # random select objects >= goal
            self.object_id_count, graph = self.add_obj(graph, k, num_obj, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids, goal_obj=True)
        
        if start:
            self.object_id_count, graph = self.setup_other_objs(graph, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids)


        ## get goal
        env_goal = {'prepare_food': []}
        for k,v in self.goal.items():
            env_goal['prepare_food'].append( {'put_{}_on_{}'.format(k, table_id): v} )
        return graph, env_goal


    def read_book(self, graph, start=True):
        max_num_objs = self.init_pool['book']['env_max_num']
        num_obj = random.randint(self.goal['book'], max_num_objs+1)

        target_ids = [node['id'] for node in graph['nodes'] if 'book' in node['class_name']]
        graph = self.remove_obj(graph, target_ids)
        self.object_id_count, graph = self.add_obj(graph, 'book', num_obj, self.object_id_count, objs_in_room=objs_in_room, goal_obj=True)
        
        except_position_ids = [node['id'] for node in graph['nodes'] if ('floor' in node['class_name'])]

        target_ids = [node['id'] for node in graph['nodes'] if 'book' in node['class_name']]


        if len(target_ids)!=0:
            target_id = random.choice(target_ids)

            if self.same_room:
                objs_in_room = self.get_obj_room(target_id)
            else:
                objs_in_room = None

            if start:
                self.object_id_count, graph = self.setup_other_objs(graph, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids)

            ## get goal
            env_goal = {'read_book': [{'read_{}'.format(target_id)}]}
        else:
            env_goal = None
            # print(self.add_goal_obj_success)

        return graph, env_goal


    def watch_tv(self, graph, start=True):
        ## add remotecontrol
        max_num_objs = self.init_pool['remotecontrol']['env_max_num']
        num_obj = random.randint(self.goal['remotecontrol'], max_num_objs+1)

        target_ids = [node['id'] for node in graph['nodes'] if 'remotecontrol' in node['class_name']]
        if len(target_ids)==0:
            self.object_id_count, graph = self.add_obj(graph, 'remotecontrol', num_obj, self.object_id_count, objs_in_room=objs_in_room, goal_obj=True)
            target_ids = [node['id'] for node in graph['nodes'] if 'book' in node['class_name']]

        assert len(target_ids)!=0
        target_id = random.choice(target_ids)

        if self.same_room:
            objs_in_room = self.get_obj_room(target_id)
        else:
            objs_in_room = None


        ## set TV off
        tv_ids = [node['id'] for node in graph['nodes'] if 'tv' in node['class_name']]
        tv_id = random.choice(tv_ids)
        graph = self.set_tv_off(graph, tv_id)

        ## set other objects
        except_position_ids = [node['id'] for node in graph['nodes'] if ('floor' in node['class_name'])]
        if start:
            self.object_id_count, graph = self.setup_other_objs(graph, self.object_id_count, objs_in_room=objs_in_room, except_position=except_position_ids)

        ## get goal
        env_goal = {'watch_tv': [ {'on_{}'.format(tv_id)}, {'grab_{}'.format(target_id)} ]}
        return graph, env_goal


    def setup_table_prepare_food(self, graph):
        graph, env_goal1 = self.setup_table(graph)
        graph, env_goal2 = self.prepare_food(graph, start=False)
        return graph, env_goal1.update(env_goal2)

    def setup_table_read_book(self, graph):
        graph, env_goal1 = self.setup_table(graph)
        graph, env_goal2 = self.read_book(graph, start=False)
        return graph, env_goal1.update(env_goal2)
    
    def setup_table_watch_tv(self, graph):
        graph, env_goal1 = self.setup_table(graph)
        graph, env_goal2 = self.watch_tv(graph, start=False)
        return graph, env_goal1.update(env_goal2)

    def setup_table_put_fridge(self, graph):
        graph, env_goal1 = self.setup_table(graph)
        graph, env_goal2 = self.put_fridge(graph, start=False)
        return graph, env_goal1.update(env_goal2)

    def setup_table_put_dishwasher(self, graph):
        graph, env_goal1 = self.setup_table(graph)
        graph, env_goal2 = self.put_dishwasher(graph, start=False)
        return graph, env_goal1.update(env_goal2)


def debug_function(comm):
    with open('data/object_info.json', 'r') as file:
        obj_position = json.load(file)


    success_edges = []
    fail_target_nodes = []

    for obj_name in obj_position['objects_grab']:
        object_id = 2000
        new_node = {'id': object_id, 'class_name': obj_name, 'properties': ['GRABBABLE'], 'states': [], 'category': 'added_object'}
        nodes = [new_node]

        for target_name in obj_position['objects_inside']:
            comm.reset()
            s, graph = comm.environment_graph()


            target_node = [node for node in graph['nodes'] if node['class_name']==target_name]
            if len(target_node)==0:
                print(target_name)
                fail_target_nodes.append(target_name)
                continue

            target_id = target_node[0]['id']

            edges = [{'from_id': object_id, 'relation_type': 'INSIDE', 'to_id': target_id}]

            
            graph['nodes'] += nodes
            graph['edges'] += edges
            success, message = comm.expand_scene(graph)
            # print(success, message)

            if success:
                success_edges.append({'from_id': obj_name, 'relation_type': 'INSIDE', 'to_id': target_name})
            else:
                print({'from_id': obj_name, 'relation_type': 'INSIDE', 'to_id': target_name})

        for target_name in obj_position['objects_surface']:
            comm.reset()
            s, graph = comm.environment_graph()


            target_node = [node for node in graph['nodes'] if node['class_name']==target_name]
            if len(target_node)==0:
                print(target_name)
                fail_target_nodes.append(target_name)
                continue

            target_id = target_node[0]['id']

            edges = [{'from_id': object_id, 'relation_type': 'ON', 'to_id': target_id}]

            
            graph['nodes'] += nodes
            graph['edges'] += edges
            success, message = comm.expand_scene(graph)
            # print(success, message)

            if success:
                success_edges.append({'from_id': obj_name, 'relation_type': 'ON', 'to_id': target_name})
            else:
                print({'from_id': obj_name, 'relation_type': 'ON', 'to_id': target_name})

    
    # with open('data/object_info_7.json', 'w') as file:
    #     json.dump(success_edges, file)


    # ## load file and save
    # with open('data/object_info_%s.json'%apartment, 'r') as file:
    #     obj_position = json.load(file)

    # objs = {}
    # for rel in obj_position:
    #     from_obj = rel['from_id']
    #     relation_type = rel['relation_type']
    #     to_obj = rel['to_id']

    #     if from_obj not in objs:
    #         objs[from_obj] = []
    #     objs[from_obj].append([relation_type, to_obj])

    # with open('data/object_info%s.json'%apartment, 'w') as file:
    #     json.dump(objs, file)

    


if __name__ == "__main__":
    # Better to not sue UnityEnv here, it is faster and it allows to create an env without agents

    ## -------------------------------------------------------------
    ## load task from json, the json file contain max number of objects for each task
    ## -------------------------------------------------------------
    with open('data/init_pool.json') as file:
        init_pool = json.load(file)



    comm = comm_unity.UnityCommunication()
    comm.reset()
    s, graph = comm.environment_graph()
    

    ## -------------------------------------------------------------
    ## get object sizes
    ## -------------------------------------------------------------

    ## step1 write object size of each apartment
    # class_name_size = {node['class_name']: node['bounding_box']['size'] for node in graph['nodes']}
    # with open('class_name_size7.json', 'w') as file:
    #     json.dump(class_name_size, file)
    
    ## -------------------------------------------------------------
    ## step2 combine object size from each apartment
    # class_name_size = {}
    # for i in range(7):
    #     with open('data/class_name_size%s.json' % str(i+1), 'r') as file:
    #         class_name_size.update(json.load(file))

    # class_name = np.unique(list(class_name_size.keys()))
    # class_name_size = {tem: class_name_size[tem] for tem in class_name}

    # with open('data/class_name_size.json', 'w') as file:
    #     json.dump(class_name_size, file)

    ## -------------------------------------------------------------
    ## step3 load object size
    with open('data/class_name_size.json', 'r') as file:
        class_name_size = json.load(file)

    ## -------------------------------------------------------------
    ## gen graph
    ## -------------------------------------------------------------
    task_names = {  1: ["setup_table", "clean_table", "put_fridge", "prepare_food", "read_book", "watch_tv"],
                    2: ["setup_table", "clean_table", "put_dishwasher", "unload_dishwasher", "put_fridge", "prepare_food", "read_book", "watch_tv"],
                    3: ["setup_table", "clean_table", "put_dishwasher", "unload_dishwasher", "put_fridge", "prepare_food", "read_book", "watch_tv"],
                    4: ["setup_table", "clean_table", "put_dishwasher", "unload_dishwasher", "put_fridge", "prepare_food", "read_book", "watch_tv"],
                    5: ["setup_table", "clean_table", "put_dishwasher", "unload_dishwasher", "put_fridge", "prepare_food", "read_book", "watch_tv"],
                    6: ["setup_table", "clean_table", "put_fridge", "prepare_food", "read_book", "watch_tv"],
                    7: ["setup_table", "clean_table", "put_dishwasher", "unload_dishwasher", "put_fridge", "prepare_food", "read_book", "watch_tv"]}
                    

    success_init_graph = []

    for apartment in range(1):
        # apartment = 3

        with open('data/object_info%s.json'%(apartment+1), 'r') as file:
            obj_position = json.load(file)

        # pdb.set_trace()bathroomcounter

        # filtering out certain locations
        for obj, pos_list in obj_position.items():
            positions = [pos for pos in pos_list if pos[1] in \
                ['kitchentable', 'cabinet', 'coffeetable', 'bench', 'chair', 'kitchencabinets']]
            obj_position[obj] = positions
        print(obj_position['wineglass'])

        num_test = 100000
        count_success = 0
        for i in range(num_test):
            comm.reset(apartment)
            s, graph = comm.environment_graph()


            ## -------------------------------------------------------------
            ## debug
            ## -------------------------------------------------------------
            # debug_function(comm)
            


            ## -------------------------------------------------------------
            ## choose tasks
            ## -------------------------------------------------------------
            # while True:
            #     task_name = random.choice(task_names[apartment+1])
            #     if task_name in ['read_book', 'watch_tv']:
            #         continue
            #     else:
            #         break
            task_name = 'setup_table'


            print('------------------------------------------------------------------------------')
            print('testing %d: %s' % (i, task_name))
            print('------------------------------------------------------------------------------')
            
            ## -------------------------------------------------------------
            ## setup goal based on currect environment
            ## -------------------------------------------------------------
            set_init_goal = SetInitialGoal(obj_position, class_name_size, init_pool, task_name, same_room=True)
            init_graph, env_goal = getattr(set_init_goal, task_name)(graph)

            
            if set_init_goal.add_goal_obj_success:
                
                success, message = comm.expand_scene(init_graph)
                print('----------------------------------------------------------------------')
                print(task_name, success, message, set_init_goal.num_other_obj)
                # print(env_goal)

                
                if not success:
                    goal_objs = []
                    goal_names = []
                    for k,goals in env_goal.items():
                        goal_objs += [int(list(goal.keys())[0].split('_')[-1]) for goal in goals]
                        goal_names += [list(goal.keys())[0].split('_')[1] for goal in goals]
                    
                    obj_names = [obj.split('.')[0] for obj in message['unplaced']]
                    obj_ids = [int(obj.split('.')[1]) for obj in message['unplaced']]

                    if task_name!='read_book' and task_name!='watch_tv':
                        intersection = set(obj_names) & set(goal_names)
                    else:
                        intersection = set(obj_ids) & set(goal_objs)
                    
                    ## goal objects cannot be placed
                    if len(intersection)!=0:
                        success2 = False
                    else:
                        init_graph = set_init_goal.remove_obj(init_graph, obj_ids)
                        success2, message2 = comm.expand_scene(init_graph)
                        success = True
                
                else:
                    success2 = True
                    

                if success2 and success:
                    success = set_init_goal.check_goal_achievable(init_graph, comm, env_goal)
                    count_success += success

                    if success:
                        comm.reset(apartment)
                        comm.expand_scene(init_graph)
                        _, init_graph = comm.environment_graph()
                        success_init_graph.append({'apartment': (apartment+1),
                                                    'task_name': task_name,
                                                    'init_graph': init_graph,
                                                    'goal': env_goal})

                    

            print('apartment: %d: success %d over %d (total: %d)' % (apartment, count_success, i+1, num_test) )

            if count_success>=10:
                break
    
    pdb.set_trace()
    pickle.dump( success_init_graph, open( "result/init1_10_same_room_simple.p", "wb" ) )
    # pickle.dump( success_init_graph, open( "result/init1_10.p", "wb" ) )
    # tem = pickle.load( open( "result/init1_10.p", "rb" ) )




        