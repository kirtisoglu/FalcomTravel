import heapq

#      LIBRARY EXPLANATIONS

# 1) heapify of a list: rearranges the elements within the list s.t. the list satisfies the heap property.

# 2) heappush(heap, element): function that adds an element to the heap while maintaining the heap invariant.

# 3) heappop(heap): function that removes and returns the smallest element from the heap. Reorganizes the heap
#                 to maintain the heap property after removing the smallest element.


def travel_time_to_source(graph, source, attr=None):

    if attr == None:
        attr = "time"

    travel_time = {
        node: float("infinity") for node in graph.nodes
    }  # Dictionary. Key: node, Value: time to source
    travel_time[source] = 0  # initialize the time of source to itself as 0.
    priority_queue = [(0, source)]  # Priority queue to store (time, node) pairs

    while priority_queue:
        current_travel_time, current_node = heapq.heappop(
            priority_queue
        )  # see explanation (3).

        if current_travel_time > travel_time[current_node]:
            continue  # If the current travel_time is greater than the recorded travel_time, skip

        for neighbor in graph[current_node].keys():
            temporary_travel_time = (
                current_travel_time + graph[current_node][neighbor][attr]
            )

            # If a shorter path is found, update the travel_time and push it to the priority queue
            if temporary_travel_time < travel_time[neighbor]:
                travel_time[neighbor] = temporary_travel_time
                heapq.heappush(priority_queue, (temporary_travel_time, neighbor))

    return travel_time


def travel_time(graph, sources, attr=None):

    if attr == None:
        attr = "time"

    t = {}  # key: (node i, facility j), value: travel time from node i to facility j
    # sources = {**existing, **possible}

    for j in sources:
        to_source = travel_time_to_source(graph, j, attr=attr)
        for i in graph.nodes:
            t[(i, j)] = to_source[i]

    return t


# Travel time by only walk. Remove the neighborhoods of stops (*).


def walk_time_to_source(grid, source):

    travel_time = {
        node: float("infinity") for node in grid.keys()
    }  # Dictionary. Key: node, Value: time to source
    travel_time[source] = 0  # initialize the time of source to itself as 0.
    priority_queue = [(0, source)]  # Priority queue to store (time, node) pairs

    while priority_queue:
        current_travel_time, current_node = heapq.heappop(
            priority_queue
        )  # see explanation (3).

        if current_travel_time > travel_time[current_node]:
            continue  # If the current travel_time is greater than the recorded travel_time, skip

        for neighbor in grid[current_node].get_node_neighbors():

            if (
                grid[neighbor].get_node_ID() == 0
                or grid[current_node].get_node_ID() == 0
            ):  # (*) do not include stop - stop

                temporary_travel_time = (
                    current_travel_time
                    + grid[current_node].get_node_distance()[neighbor]
                )

                # If a shorter path is found, update the travel_time and push it to the priority queue
                if temporary_travel_time < travel_time[neighbor]:
                    travel_time[neighbor] = temporary_travel_time
                    heapq.heappush(priority_queue, (temporary_travel_time, neighbor))

    return travel_time


def walk_time(grid, existing, possible):

    t = {}
    sources = {**existing, **possible}

    for j in sources.keys():
        to_source = walk_time_to_source(grid, j)
        for i in grid.keys():
            t[(i, j)] = to_source[i]

    return t
