from discord.ext import commands

from utils.config import conf

LANGUAGES = conf['hl_langs']


def return_lang_hl(input_string) -> str:
    for possible_suffix in LANGUAGES:
        if input_string.endswith(possible_suffix):
            return possible_suffix
    return 'sh'


def pluralize(inp, value):
    if isinstance(value, list):
        inp = inp + 's' if len(value) != 1 else inp
    if isinstance(value, int):
        inp = inp + 's' if value != 1 else inp
    return inp


class BoolConverter(commands.Converter):
    async def convert(self, ctx, argument):
        true_values = ['on', 'yes', 'true', 'y']
        false_values = ['off', 'no', 'false', 'n']
        if argument.lower() in true_values:
            return True
        elif argument.lower() in false_values:
            return False
        else:
            raise commands.BadArgument('Input could not be converted into a true or false result')

def prettify_text(content):
    return content.replace('_', ' ').capitalize()
