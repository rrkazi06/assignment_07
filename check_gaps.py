from rivals import *
import pandas as pd

menus = pd.read_csv("cache/menus.csv")
matches = pd.read_csv("data/item_matches.csv")

tagged = add_canonical(menus, matches)
print(tagged.groupby("cafe")["canonical"].apply(lambda s: s.notna().sum()))

g = gap_analysis(tagged)
print(g["where"].value_counts())
