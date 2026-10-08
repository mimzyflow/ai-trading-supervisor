# Audit des simulations du 8 octobre 2026

Aucune stratégie vérifiée ici ne justifie une activation réelle. Les résultats
ci-dessous distinguent les backtests Freqtrade, la recherche quotidienne du
simulateur Python et les portefeuilles papier prospectifs. La copie locale V3
`62f7309` diffère du code Oracle contrôlé au début de cet audit, `a1849ff`.

## Archives Freqtrade relues directement

21 archives ZIP privées ont été relues sur le Mac : 20 sous
`/Users/mimocisse/Projects/ai-trading-supervisor/backtests/results/` et une sous
`user_data/backtest_results/` du même projet. Leur JSON embarqué et les frais des
trades ont été contrôlés. Les fichiers bruts restent hors Git.

Capital fictif 100 EUR, allocation 20 EUR, maximum deux positions. Les résultats
retenus dans ce tableau utilisent 0,8 % de frais **par côté**, environ 1,6 %
aller-retour, sans modèle historique de spread/glissement.

| Stratégie native | Fenêtre effective | Clôtures | Rendement portefeuille | PF | Baisse maximale |
|---|---|---:|---:|---:|---:|
| MoussaBaseline 1h | 9 janvier au 31 mars 2026 | 32 | -8,7105 % | 0,1071 | 8,7105 % |
| MoussaBaseline 1h | 9 avril au 30 juin 2026 | 49 | -16,8754 % | 0,0005 | 16,8754 % |
| MoussaTrendGuard 1h | 10 janvier au 31 mars 2026 | 15 | -4,0375 % | 0,3312 | 4,0375 % |
| MoussaTrendGuard 1h | 10 avril au 30 juin 2026 | 15 | -5,6995 % | 0,1321 | 5,6995 % |
| MoussaRegimeTrend 4h | archives T1 2026 | 0 | 0 % | sans observation | 0 % |
| MoussaRegimeTrend 4h | archives T2 2026 | 3 | -1,9239 % | 0 | 1,9239 % |
| MoussaSmallCapMomentum 4h | 11 juillet 16h au 2 octobre 20h UTC | 30 | +7,0644 % | 1,4090 | 3,6614 % |

Preuves identifiables : archives `2026-10-03_00-18-01`, `00-16-41`, `00-18-16`,
`00-16-54`, `00-20-06`, `00-20-35` et `00-33-26` respectivement.

Le gain small/mid-cap dépend d'ARB/EUR : +6,0034168 EUR sur +7,0644 EUR, soit
84,98 % du résultat total. Les pertes et les contributions des autres actifs
ont été conservées. Les validations indépendantes T1/T2, les variantes pullback,
regime et breadth sont documentées dans [BACKTESTS.md](BACKTESTS.md) ; leurs
archives brutes n'étaient pas présentes dans les 21 ZIP locaux relus. Ce document
ne présente donc pas cette partie comme une nouvelle reproduction numérique.

## V2 et V3 : ne pas confondre les moteurs

Le rapport local `ai-trading-v3/user_data/reports/autonomy.json`, daté du
6 octobre 17:48 UTC, contient huit templates V2 quotidiens, tous inéligibles.
Certains résultats de sélection sont positifs, mais les fenêtres d'entraînement
perdent, le nombre de trades est faible et les baisses dépassent 5 %. Ce rapport
local est ancien et provient d'un diagnostic avec risque moteur non vérifié.
Il ne remplace pas les observations Oracle du 8 octobre.

Ses trois challengers V3 quotidiens sont tous rejetés :

| Challenger quotidien, ancien code local | Rendement global | PF | Baisse maximale | Clôtures |
|---|---:|---:|---:|---:|
| regime_momentum | -6,1664 % | 0,5372 | 8,1945 % | 26 |
| triple_barrier | -2,2188 % | 0,7341 | 6,2393 % | 18 |
| slow_breakout | -0,5932 % | 0,9004 | 5,2058 % | 11 |

Chaque challenger a également quatre fenêtres chronologiques distinctes. Tous
les rendements de fenêtre de cette copie sont négatifs ou nuls. Le résultat
global ne cumule pas quatre portefeuilles indépendants : son arrêt de risque
peut intervenir dès la première fenêtre.

Ces calculs utilisent des bougies **quotidiennes**, des moyennes simples et des
durées en séances. Les classes natives `MoussaV3RegimeMomentum` et
`MoussaV3TripleBarrier` utilisent des bougies 1h, EMA, ADX et RSI ;
`MoussaV3SlowBreakout` utilise des bougies 4h. Les paramètres d'entrée, ROI,
trailing et sorties ne correspondent pas exactement au simulateur quotidien.
Exemple : `triple_barrier.max_hold=30` séances, contre une sortie native après
72 heures. Un verdict quotidien n'est donc pas un backtest de la classe native.

L'unique manifeste V3 local `research_results/20261006T172947-212194/manifest.json`
décrit une commande préparée pour `MoussaV3RegimeMomentum` sur T1 BTC/ETH 1h.
Il ne contient ni `exit_code`, ni archive de résultat. Les scripts de
lookahead/recursive sont présents ; aucune preuve de leur exécution réussie
n'a été retrouvée dans ces artefacts locaux.

## Deux corrections de causalité

Les anomalies suivantes ont été reproduites avec des données synthétiques sur
le moteur V3 avant correction, puis couvertes par
[test_engine_causality.py](../tests/test_engine_causality.py).

1. Le calcul de quantité à l'ouverture utilisait le volume final de cette même
   séance. Avec une ouverture à 10 identique et le même passé, changer seulement
   le volume futur de 10 000 à 10 changeait la quantité crypto de 2 à 0,1.
   [engine.py](../research_lab/engine.py) utilise désormais le volume de la
   dernière séance clôturée. La première séance sert de warm-up de liquidité.
2. Les high/low intraday étaient examinés avant les sorties dues à l'ouverture
   pour temps maximal, tendance du cours précédent ou risque portefeuille.
   À un timeout avec ouverture 11, modifier seulement le high futur de 11,11
   à 12,5 remplaçait une sortie à profit nul par un take-profit de +1,60.
   Les sorties connues à l'ouverture passent désormais avant ces barrières.
   Lorsque seule la trajectoire intraday est ambiguë, le stop reste prioritaire.

L'adaptateur [equity_experiment.py](../research_lab/equity_experiment.py) conserve
désormais les vrais volumes et laisse le moteur appliquer un seul décalage.
Le descriptif des achats du benchmark utilise aussi la séance précédente.
`scripts/simulate_equities.py` appelait déjà directement le moteur et ne
nécessitait aucun décalage supplémentaire. Les tests de splits/dividendes ont
une séance de warm-up, afin de conserver une position avant l'événement.

Validation ciblée : 7 tests de causalité, 6 tests d'expérience actions,
46 tests du laboratoire et 3 tests V3, tous réussis. Cette note ne remplace pas
la validation complète et la vérification de déploiement.

## Recherche suivante et limites conservées

- Conserver les anciens résultats et plans avec leurs empreintes. Le moteur
  corrigé modifie `implementation_sha256` : les anciens verdicts ne décrivent
  plus ce code. Utiliser la procédure de [reprise](RESEARCH_RESUME.md), sans
  effacer des fenêtres consommées ni antidater un nouveau gel.
- Donner un identifiant distinct aux stratégies quotidiennes et natives.
  Comparer les classes réellement exécutées par le même moteur et les mêmes
  données avant toute conclusion de performance.
- Pour V3, ajouter un scénario stressé explicite au gate : `v3_challengers.evaluate`
  n'appelle actuellement que `costs(bundle)` ; la présence d'un stress dans la
  recherche V2 ne prouve pas que V3 passe les frais renforcés.
- Le PBO local à zéro porte sur trois challengers et seulement quatre fenêtres.
  Ce chiffre ne démontre aucune rentabilité. DSR et bootstrap utilisent les
  échantillons observés et ne reconstruisent ni régimes absents, ni indépendance
  des trades, ni toutes les variantes déjà essayées.
- L'univers crypto courant classé par liquidité actuelle conserve un biais de
  survie/listing. Les minimums de commande réels et les spreads historiques ne
  sont pas validés par le simulateur. Les frais restent des scénarios.
- Garder les rapports prospectifs crypto/actions distincts des essais
  historiques, avec date d'observation, dernière séance, version du code,
  arrêt de risque, frais, compte de trades et motifs de rejet.

Aucun paramètre de stratégie n'a été retouché sur les résultats observés. Aucun
résultat historique n'a été recalculé dans son ancien dossier ni écrasé par ce
correctif. Les clés, dépôts et ordres réels restent hors périmètre.
