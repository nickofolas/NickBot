from discord.ext import commands

from dateparser import parse

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


class HumanTime(commands.Converter):
    @staticmethod
    def parse_input(to_parse):
        settings = {
            'TIMEZONE': 'UTC',
            'TO_TIMEZONE': 'UTC',
            'PREFER_DATES_FROM': 'future'
        }
        out = parse(to_parse, settings=settings)
        return out

    @staticmethod
    def check(time, ctx):
        if not time:
            raise commands.BadArgument('Invalid time')
        elif time < ctx.message.created_at:
            raise commands.BadArgument('Time must be in the future')

    async def convert(self, ctx, argument):
        time = await ctx.bot.loop.run_in_executor(None, self.parse_input, argument)
        self.check(time, ctx)
        return time


def prettify_text(content):
    return content.replace('_', ' ').capitalize()
