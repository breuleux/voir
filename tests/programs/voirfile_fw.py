def instrument_forward(ov):
    yield ov.phases.init
    ov.given.where("n") >> ov.log
