import osmnx as ox

# To plot a redistricting with a nice color distribution, get n evenly-spaced colors from some matplotlib colormap
ox.plot.get_colors(n=5, cmap="plasma")


# get node colors by linearly mapping an attribute's values to a colormap. We can use this to map travel times (or statistical results).
nc = ox.plot.get_node_colors_by_attr(G, attr="y", cmap="plasma")
fig, ax = ox.plot_graph(G, node_color=nc, edge_linewidth=0.3)
