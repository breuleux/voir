
Guide
=====

Phases
~~~~~~

A program run with ``voir`` goes through a sequence of phases. After each phase, an :ref:`instrument<Instruments>` can do certain things.

Refer to the code of the following instrument to see what the phases are and what you may do in-between them:

.. code-block:: python

    def instrument_show_phases(ov):
        yield ov.phases.init
        # Voir has initialized itself. You can add command-line arguments here.

        yield ov.phases.parse_args
        # The command-line arguments have been parsed.

        yield ov.phases.load_script
        # The script has been loaded: its imports have been done, its functions defined,
        # but the top level statements have not been executed. You can perform some
        # manipulations prior to the script running, e.g. monkey-patch functions.

        yield ov.phases.run_script
        # The script has finished.

        yield ov.phases.finalize

.. note::

    Voir logs events in the 3rd file descriptor if it is open, or to the ``$DATA_FD`` descriptor. Consequently, if you run ``voir script.py 3>&1`` you should be able to see the list of phases.


Instruments
~~~~~~~~~~~

An *instrument* is a function defined in ``voirfile.py`` that begins with ``instrument_``, or a value in the ``__instruments__`` dictionary of the same file. It takes one argument, the :class:`~voir.overseer.Overseer`, and its purpose is to do things at various points during execution. In order to do so, it is implemented as a generator function: all it has to do is yield one of the overseer's phases, and the overseer will return to the instrument after that phase is finished. The overseer defines the order, so you only need to yield the phases you want to wait for.

Example
+++++++

This instrument adds a ``--time`` command-line argument to Voir. When given, it will calculate the time the script took to load and import its dependencies, and then the time it took to run, and it will print out these times.

.. code-block:: python

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

The ``--time`` argument goes BEFORE the script, so you would invoke it like this:

.. code-block:: bash

    voir --time script.py SCRIPT_ARGUMENTS ...
