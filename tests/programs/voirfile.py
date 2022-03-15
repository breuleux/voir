def instrument_greet(ov):
    print("<hey>")
    yield ov.phases.run_script
    print("<bye>")
