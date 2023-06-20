
# Voir

[Documentation](https://voir.readthedocs.io)

Voir lets you wrap your scripts to display certain values or metrics and/or analyze their behavior. To use Voir:

* Add a file named `voirfile.py` in the current directory.
* Define one or more instruments in `voirfile.py`.
* Run `voir script.py` instead of `python script.py`.

Here are a few things you can do:

* Patch functions and libraries prior to running a script
* Log CPU or GPU usage
* Manipulate or log streams of data coming from the script
* Show a nifty dashboard


## Functioning

An *instrument* is a function defined in `voirfile.py` that begins with `instrument_`, or a value in the `__instruments__` dictionary of the same file. It takes one argument, the *overseer*, and its purpose is to do things at various points during execution. In order to do so, it is implemented as a generator function: all it has is to yield one of the overseer's phases, and the overseer will return to the instrument after that phase is finished. The overseer defines the order, so you only need to yield the phases you want to wait for.

```python
def instrument_show_phases(ov):
    yield ov.phases.init
    # Voir has initialized itself. You can add command-line arguments here.

    yield ov.phases.parse_args
    # The command-line arguments have been parsed.

    yield ov.phases.load_script
    # The script has been loaded: its imports have been done, its functions defined,
    # but the top level statements have not been executed. You can perform some
    # manipulations prior to the script running.

    yield ov.phases.run_script
    # The script has finished.

    yield ov.phases.finalize
```

Voir also logs events in the 3rd file descriptor if it is open, or to the `$DATA_FD` descriptor. Consequently, if you run `voir script.py 3>&1` you should be able to see the list of phases.

<!-- If `$DATA_FD=1` Voir will smuggle data into the standard output by abusing ANSI control codes, so it won't be visible in the terminal. -->

### Example

This instrument adds a `--time` command-line argument to Voir. When given, it will calculate the time the script took to load and import its dependencies, and then the time it took to run, and it will print out these times.

```python
def instrument_time(ov):
    yield ov.phases.init

    ov.argparser.add_argument("--time", action="store_true")

    yield ov.phases.parse_args

    if ov.options.time:
        t0 = time.time()
        
        yield ov.phases.load_script
        
        t1 = time.time()
        print(f"Load time: {(t1 - t0) * 1000}ms")
        
        yield ov.phases.run_script
        
        t2 = time.time()
        print(f"Run time: {(t2 - t1) * 1000}ms")
```

The `--time` argument goes BEFORE the script, so you would invoke it like this:

```bash
voir --time script.py SCRIPT_ARGUMENTS ...
```
