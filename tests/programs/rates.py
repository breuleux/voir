import time

from voir import give, iterate

if __name__ == "__main__":
    batches = [[i] * 10 for i in range(10)]
    for batch in iterate("stuff", batches, report_batch=True):
        time.sleep(0.1)
        give(loss=1 / (1 + sum(batch)))
