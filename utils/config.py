import yaml

with open('utils/config.yml', 'r') as config:
    con = yaml.safe_load(config)

conf = dict(con)
