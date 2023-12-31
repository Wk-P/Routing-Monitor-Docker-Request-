import docker, time, json, os
import multiprocessing

# NODE name, address, client instance
def generate_nodes_info_pool(nodes, service_name):
    nodes_info_pool = []
    for node in nodes:
        if node.attrs['Spec']['Role'] == "worker":
            # test
            # print(f"{node.attrs['Description']['Hostname']}: {node.attrs['Status']['Addr']}")

            ip = node.attrs['Status']['Addr']
            port = 2375

            node_address = f'{ip}:{port}'

            node_info = {
                "name": node.attrs['Description']['Hostname'],
                "address": node_address,
                "client": docker.DockerClient(base_url=f"tcp://{node_address}")
            }

            # append single node info into information pool

            node_info['containers'] = []
            
            containers = node_info['client'].containers.list()

            # get the containers for every node
            
            # find container by node_name and service name
            for c in containers:
                container_name = c.name
                if container_name.split('.')[0] == service_name:
                    try:
                        # add container object in nodes_info
                        node_info['containers'].append(c)
                    except:
                        print(c)
                        exit(1)

            nodes_info_pool.append(node_info)
    return nodes_info_pool



# def update_data(client, container, manager_client, service_name, scaled):
def monitor_node(nodes_info):
    resources = []
    cpu_percent_limit = 50
    for node in nodes_info:
        client = node['client']

        for container in node['containers']:

            # get CPU stats data
            stats_data = client.containers.get(container.id).stats(stream=False)

            pre_cpu_stats = stats_data['precpu_stats']
            cpu_stats = stats_data['cpu_stats']

            cpu_usage = cpu_stats['cpu_usage']
            print(cpu_usage)
            pre_cpu_usage = pre_cpu_stats['cpu_usage']

            system_cpu_usage = cpu_stats['system_cpu_usage']
            online_cpus = cpu_stats['online_cpus']

            # calculate
            cpu_delta = cpu_usage['total_usage'] - pre_cpu_usage['total_usage']
            system_delta = system_cpu_usage - pre_cpu_stats['system_cpu_usage']

            cpu_percent = 0.0
            if system_delta > 0.0:
                cpu_percent = (cpu_delta / system_delta) * online_cpus * 100

            

            # memory stats
            memory_stats = stats_data['memory_stats']
            memory_usage = memory_stats['usage'] / 1024 / 1024
            memory_limit = memory_stats['limit'] / 1024 / 1024 / 1024


            print(f"Node {node['name']} Container {container.name.split('.')[0]} CPU Percent is {cpu_percent: .2f} %")
            print(f"Node {node['name']} Container {container.name.split('.')[0]} MEM Usage is {memory_usage: .2f} MiB / {memory_limit: .2f} GiB")


            file_path = "training.txt"
            with open(file_path, 'a', encoding='utf-8') as file:
                file.write(f"{node['address']} {cpu_percent} {memory_usage/memory_limit}\n")


            # scaling up
            data = {}
            if cpu_percent >= cpu_percent_limit:
                # route_table change
                data = {
                    'node': node['name'],
                    'status': 'running',
                    'HS': 'up',
                    'VS': None,
                    'cpu-usage': cpu_percent,
                    'mem-usage': memory_usage,
                    'mem-limit': memory_limit
                }
            else:
                data = {
                    'node': node['name'],
                    'status': 'running',
                    'HS': None,
                    'VS': None,
                    'cpu-usage': cpu_percent,
                    'mem-usage': memory_usage,
                    'mem-limit': memory_limit
                }

            resources.append(data)

    return resources


def active_node(node_name):
    password = 123321
    active_cmd = f'sudo docker node update --availability active {node_name}'
    os.system('echo %s | sudo -S %s' % (password, active_cmd))

    if os.system(active_cmd) == 0:
        return True
    else:
        return False



def create_monitor():
    default_client = docker.from_env()
    service_name = "node-service"
    nodes = default_client.nodes.list()

    # get node requests url and port (json list : NAME, ADDRESS, CLIENT, CONTAINERS)
    nodes_info = generate_nodes_info_pool(nodes, service_name)

    return nodes_info



def active_one_node(nodes_info, route_table):
    

    node_address = None
    for node in route_table:
        if node['status'] == 'N':
            node_address = node['address'][7:-5]
            node['status'] = 'Y'
            print(f"In active {route_table}") 

    if node_address is not None:
        for node in nodes_info:
            if node['address'][:-5] == node_address and active_node(node['name']):
                return {'name': node['name'], 'status': 'Start running success'}
        
        return {'type': 'text', 'msg': {'name': node['name'], 'status': 'Start running failed'}}
    else:
        return {'type': 'error', 'msg': "No matching node or node has been started"}


def process_for_monitor(nodes_info, route_table):
    while True:
        # print(f"In monitor {table}")  # Access shared route_table
        values = monitor_node(nodes_info=nodes_info)
        for value in values:
            if value['HS'] == 'up':
                active_one_node(nodes_info=nodes_info, route_table=route_table)
            else:
                pass

if __name__ == "__main__":
    route_table = [
        {
            "address": "http://192.168.56.103:8080",
            'status': "Y"
        },
        {
            "address": "http://192.168.56.105:8080",
            'status': "Y"
        }
    ]

    nodes_info = create_monitor()

    # Create a separate process for process_for_monitor
    monitor_process = multiprocessing.Process(target=process_for_monitor, args=(nodes_info, route_table))
    monitor_process.start()

    