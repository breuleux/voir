def header(ov):
    yield ov.phases.init
    print("/////")


def greet(ov):
    yield ov.phases.init
    print("<bonjour>")
    yield ov.phases.run_script
    print("<bonsoir>")


__instruments__ = [
    {
        "greet": greet,
        "header": header,
    }
]
