# Runbook de mise en service

## Phase 1 - automatique
- [x] Préparer Freqtrade en Docker.
- [x] Configurer Kraken en dry-run.
- [x] Limiter la V1 au spot.
- [x] Créer une stratégie baseline testable.
- [x] Créer le rapport horaire local.
- [ ] Déployer sur Oracle.
- [ ] Vérifier le fonctionnement continu 24/7.

## Phase 2 - intervention Moussa
- [ ] Créer/valider le compte Kraken et l'identité.
- [ ] Activer la sécurité du compte et la 2FA.
- [ ] Créer une clé API dédiée au bot.
- [ ] Autoriser lecture + ordres uniquement.
- [ ] Ne jamais autoriser les retraits.
- [ ] Déposer le capital choisi, initialement envisagé autour de 100 EUR.

## Phase 3 - validation avant argent réel
- [ ] Laisser tourner le dry-run plusieurs semaines.
- [ ] Backtester plusieurs fenêtres de marché.
- [ ] Lancer lookahead-analysis et recursive-analysis.
- [ ] Examiner rendement, drawdown, taux de réussite, fréquence et frais.
- [ ] Modifier la stratégie uniquement sur la base de tests reproductibles.
- [ ] Valider manuellement le passage en réel.

## Phase 4 - réel, uniquement après validation explicite
- Créer `user_data/config.private.json` hors Git avec les clés Kraken.
- Passer `dry_run` à false seulement après validation de Moussa.
- Conserver une mise limitée et un nombre maximum de positions.
- Garder les rapports et alertes techniques actifs.
