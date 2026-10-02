# Mac standby

Le Mac est un secours de développement et de simulation. Il ne doit jamais devenir une seconde instance réelle active en parallèle d'Oracle.

## Runtime validé sur ce Mac Intel
- uv 0.12.18
- Python 3.12.14
- Freqtrade 2026.6
- CCXT 4.5.61
- cryptography 46.0.6
- scipy 1.18.1

La version 2026.9 de Freqtrade tire CCXT récent puis cryptography 50, dont la compilation native échoue sur ce macOS Intel sans OpenSSL/pkg-config système. Le pin 2026.6 + CCXT 4.5.61 + cryptography 46.0.6 évite Homebrew et reste réservé au standby Mac.

## Installation reproductible
```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python \
  'cryptography==46.0.6' 'ccxt==4.5.61' 'freqtrade==2026.6' scipy
```

Le Mac ne reçoit aucune clé Kraken tant que la bascule de secours réelle n'a pas été conçue et validée. En exploitation normale, Oracle reste l'unique moteur.
