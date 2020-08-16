"""
neo Discord bot
Copyright (C) 2020 nickofolas

neo is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

neo is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with neo.  If not, see <https://www.gnu.org/licenses/>.
"""
import re
import ast
import inspect
import traceback

import import_expression

__all__ = ('NeoEval',)

def insert_yield(body):
    if not isinstance(body[-1], ast.Expr):
        return
    if not isinstance(body[-1].value, ast.Yield):
        yield_st = ast.Yield(body[-1].value)
        ast.copy_location(yield_st, body[-1])
        yield_expr = ast.Expr(yield_st)
        ast.copy_location(yield_expr, body[-1])
        body[-1] = yield_expr

code_base = 'async def func(scope):' \
            '\n  try:' \
            '\n    pass' \
            '\n  finally:' \
            '\n    scope.update(locals())' 

def wrap_code(code_input):
    code_in = import_expression.parse(code_input)
    base = import_expression.parse(code_base)
    try_block = base.body[-1].body[-1].body
    try_block.extend(code_in.body)
    ast.fix_missing_locations(base)
    insert_yield(try_block)
    return base


def format_exception(error):
    fmtd_exc = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    formatted = ''.join(re.sub(r'File ".+",', 'File "<eval>"', fmtd_exc))
    return formatted


def clear_intersection(dict1, dict2):
    for key in dict1.keys():
        if dict2.get(key):
            del dict2[key]


class NeoEval:
    def __init__(self, *, code, context, scope):
        self.code = wrap_code(code)
        self.context = context
        self.scope = scope

    def __aiter__(self):
        import_expression.exec(compile(self.code, "<eval>", "exec"), self.context)
        _aexec = self.context['func']
        return self.get_results(_aexec, self.scope)

    async def get_results(self, func, *args, **kwargs):
        if inspect.isasyncgenfunction(func):
            async for result in func(*args, **kwargs):
                yield result
        else:
            yield await func(*args, **kwargs) or ''


