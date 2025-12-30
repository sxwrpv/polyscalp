import logging
import os
from datetime import datetime

def setup_logger(log_dir: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    log = logging.getLogger("polyscalp")
    log.setLevel(logging.INFO)

    if not log.handlers:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        fh = logging.FileHandler(os.path.join(log_dir, f"bot_{ts}.log"), encoding="utf-8")
        sh = logging.StreamHandler()

        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        fh.setFormatter(fmt)
        sh.setFormatter(fmt)

        log.addHandler(fh)
        log.addHandler(sh)

    return log