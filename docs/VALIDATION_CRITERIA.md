# Critères de validation fixés d'avance (simulation uniquement)

Fixés le 13 octobre 2026, **avant** l'observation des comptes concernés
(expérience `market-room-100eur-20261009` et témoin `control-stops-20261013`).
Seuils dans `config/validation-thresholds.json`, vérification dans
`supervisor/validation.py::evaluate`, tests dans `tests/test_validation.py`.
Un seuil ne se modifie pas au vu des résultats ; tout changement passe par une
PR datée avec nouvel `id`. **Aucun verdict n'autorise un ordre réel**
(`real_money_eligible` reste `false`).

## Candidat (verdict `candidate`) — toutes les conditions
| Critère | Seuil |
|---|---|
| Clôtures | ≥ 30 |
| Durée d'observation prospective | ≥ 30 jours depuis le premier trade |
| Profit factor net de frais | > 1,2 |
| Baisse maximale observée | < 5 % |
| Rendement réalisé net | > 0 % |
| Part des frais dans le gain brut | ≤ 50 % |

## Arrêt (verdict `stop`) — une seule condition suffit
| Critère | Seuil |
|---|---|
| Baisse maximale | ≥ 5 % |
| Pertes consécutives | ≥ 10 |
| Profit factor après 20 clôtures | < 0,8 |

Sinon : `continue` (observation à poursuivre), avec les motifs listés.

## Règles
- Donnée manquante ou non vérifiée = critère non satisfait, jamais supposé favorable.
- Comptes comparés séparément ; pas de cumul entre bases, ni avec les backtests.
- Un verdict `stop` est un signal de revue pour Moussa/Manager : la fonction
  n'arrête aucun bot elle-même et ne modifie aucune politique.
- Même un `candidate` exige ensuite une revue humaine et une période de
  confirmation supplémentaire ; il ne vaut pas preuve de rentabilité.
