
What is Voir?
=============

Voir lets you wrap your scripts to display certain values or metrics and/or analyze their behavior. To use Voir:

* Add a file named ``voirfile.py`` in the current directory.
* Define one or more :ref:`instruments<Instruments>` in ``voirfile.py``.
* Run ``voir script.py`` instead of ``python script.py``.

Here are a few things you can do:

* Patch functions and libraries prior to running a script
* Log CPU or GPU usage
* Manipulate or log streams of data coming from the script
* Show a nifty dashboard
