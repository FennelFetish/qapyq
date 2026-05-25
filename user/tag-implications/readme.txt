Place CSV files into this folder to load implied tags.
qapyq expects a header row at the top with these column names:
    antecedent_name
    consequent_name

If a "status" column exists, only rows with "active" are loaded.
Other columns are ignored.

When applying rules to tags, the consequent_name is removed when antecedent_name exists.
Transitive implications are also removed: A -> B -> C, removes B and C when tag A exists.
