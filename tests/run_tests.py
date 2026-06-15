import os
import sys
import importlib
import traceback

# Ensure repo root is in sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

tests_dir = os.path.dirname(__file__)
modules = []
for fn in os.listdir(tests_dir):
    if fn.startswith('test_') and fn.endswith('.py') and fn != 'run_tests.py':
        modules.append(fn[:-3])

results = []
for modname in modules:
    try:
        mod = importlib.import_module('tests.' + modname)
    except Exception:
        print(f"ERROR importing {modname}:\n", traceback.format_exc())
        results.append((modname, False, 'import_error'))
        continue
    # Execute functions starting with test_
    for name in dir(mod):
        if name.startswith('test_'):
            func = getattr(mod, name)
            if callable(func):
                try:
                    print(f"RUNNING {modname}.{name}()")
                    func()
                    print(f"OK {modname}.{name}")
                    results.append((f"{modname}.{name}", True, ''))
                except AssertionError as e:
                    print(f"FAIL {modname}.{name}: AssertionError: {e}")
                    results.append((f"{modname}.{name}", False, 'assert'))
                except Exception:
                    print(f"ERROR {modname}.{name}:\n", traceback.format_exc())
                    results.append((f"{modname}.{name}", False, 'error'))

# Summary
passed = sum(1 for r in results if r[1])
failed = len(results) - passed
print('\nSUMMARY:')
print(f'  Modules discovered: {len(modules)}')
print(f'  Tests run: {len(results)}')
print(f'  Passed: {passed}')
print(f'  Failed: {failed}')

if failed > 0:
    sys.exit(1)
else:
    sys.exit(0)
