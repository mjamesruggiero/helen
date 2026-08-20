from helen.load import load_raw, load_category_rules, load_check_notes
from helen.clean import clean
from helen.categorize import categorize
from helen.enrich import apply_check_notes
df = apply_check_notes(categorize(clean(load_raw('/Users/michaelruggiero/Desktop/debris/2026_08_10_checking.csv')), load_category_rules()), load_check_notes())
u = df[(df['is_outflow']) & (df['category']=='Uncategorized')]
print(u.groupby('merchant')['amount'].agg(['count','sum']).sort_values('sum').head(20).to_string())
