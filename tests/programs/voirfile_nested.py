def instrument_header(ov):
    yield ov.phases.init
    print("~~~~~")


def greet(ov):
    yield ov.phases.init
    print("<heyoo>")
    yield ov.phases.run_script
    print("<bye>")


instrument_list = [{"greet": greet}]
