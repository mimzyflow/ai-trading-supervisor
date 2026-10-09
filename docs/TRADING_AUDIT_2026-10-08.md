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

### Recalcul distinct avec le moteur corrigé

Le diagnostic privé `.runtime/audit-20261008/v3-corrected.json`, calculé le
8 octobre à 15:15:49 UTC, utilise les 12 actifs crypto et les 720 séances du
bundle Oracle, du 19 octobre 2024 au 8 octobre 2026. Il est conservé séparément
des résultats ci-dessus : aucun ancien chiffre ni artefact n'a été remplacé.
Les paramètres des challengers sont inchangés.

| Challenger quotidien, moteur corrigé | Rendement global | PF | Baisse maximale | Clôtures | Verdict |
|---|---:|---:|---:|---:|---|
| regime_momentum | -3,0073 % | 0,7693 | 5,6298 % | 29 | rejeté |
| triple_barrier | -4,0729 % | 0,6006 | 5,2722 % | 20 | rejeté |
| slow_breakout | -1,7791 % | 0,7847 | 5,8648 % | 16 | rejeté |

Les trois variants restent rejetés : gains nets négatifs, PF inférieur à 1,20,
moins de 30 clôtures et au moins une fenêtre chronologique défavorable. Le
seuil d'arrêt de 5 % peut être dépassé par les gaps et les frais ; ce tableau
ne prétend pas garantir une perte maximale. Ce recalcul quotidien reste un
diagnostic rétrospectif crypto, distinct des actions et des classes Freqtrade
1h/4h. Il ne constitue aucun nouveau test futur.

Empreinte SHA-256 du fichier corrigé :
`098d8331d87ae710c2587d669ae1927e69ea9bea90e80c6432c283cf1ca4e488`.
Le JSON conserve également les empreintes du bundle et de l'implémentation.

## Actions : archives vérifiées et portefeuille prospectif

Les 72 résultats du 4 octobre ont été relus dans les archives privées du projet
`improvements-20261004/trading/research_results/equity-experiment-20261004-v1/`.
Les 72 identifiants fenêtre/variante/coûts sont distincts ; les six empreintes
des sorties, l'empreinte du plan et celles du code d'origine correspondent.
Le bundle contient 1 342 séances par titre, SOFI et U, du 1er juin 2021 au
2 octobre 2026. Le protocole était fixé au commit `5c9d69d` avant calcul.

Ces 72 calculs regroupent quatre stratégies, deux références cash/achat-
conservation, quatre fenêtres et trois scénarios de coûts. Ils ne correspondent
donc pas à 72 stratégies indépendantes. Budget fictif 100 USD, allocation
maximale 20 USD par titre, actions entières ; scénario conservateur à 0,1 %
par côté, minimum 1 USD par ordre et glissement 0,1 % par côté.

| Fenêtre | Rendement des quatre stratégies, scénario conservateur | Clôtures par stratégie | Achat-conservation |
|---|---:|---:|---:|
| 2023 | -5,1659 à -0,6928 % | 1 ou 2 | +19,142 % |
| 2024 | +3,7550 % | 1 | +3,665 % |
| 2025 | -6,7396 à -5,3014 % | 2 | +9,139 % |
| 2026 jusqu'au 2 octobre | 0 % | 0 | 0 % |

Aucun candidat robuste n'est retenu. Le gain 2024 repose sur une seule clôture.
En 2026, les tentatives d'entrée ne produisent aucun achat faisable sous le
plafond de 20 USD : le zéro indique du cash inutilisé. Le scénario sans
commission est une hypothèse séparée et ne réhabilite pas les variantes.
Les résultats complets restent dans
[le rapport historique](EQUITY_SIMULATION_RESULTS_2026-10-04.md), sans recalcul
dans son ancien dossier. Ce laboratoire à deux titres ne remplace pas les
observations du portefeuille prospectif à huit titres déployé depuis octobre.

### Corrections du portefeuille papier livrées

[equity_paper.py](../research_lab/equity_paper.py) conserve les états, capital et
transactions existants. Il ajoute `execution_revision=paper_engine_v2` et une
date d'activation ; les métriques cumulées continuent d'inclure l'historique
antérieur à cette révision.

- Les stops protègent maintenant V2 comme V3. Un gap sous le stop utilise le
  prix d'ouverture ; un stop intraday passe avant un objectif de gain lorsque
  la séquence high/low est inconnue. Les coûts restent appliqués à la sortie.
- Une baisse portefeuille de 5 % déclenche un halt persistant et la liquidation
  au premier prix modélisé disponible : ouverture pour un dépassement connu à
  l'ouverture, clôture pour un dépassement constaté à la clôture. Les frais de
  chaque nouvel achat sont contrôlés avant d'autoriser le suivant. Un redémarrage
  ou une récupération ultérieure n'efface pas le halt ni la perte historique.
- `held_sessions` et `held_as_of` remplacent l'index glissant du bundle pour la
  durée maximale. L'âge d'une ancienne position est récupéré seulement si sa
  date d'entrée et la dernière séance traitée sont connues. Sinon,
  `paper_blocked/age_history_unavailable` conserve le portefeuille sans inventer
  une durée ni réinitialiser le capital.
- Les filtres V3 volume et ATR utilisent uniquement les séances précédemment
  clôturées, comme le moteur quotidien corrigé. Aucun seuil de stratégie n'est
  modifié selon les performances observées.

[equity_live.py](../research_lab/equity_live.py) conserve les dates et codes des
splits/dividendes annoncés, dans une liste bornée ; des métadonnées malformées
sont refusées. Une opération sur titre dans les nouvelles séances à traiter
produit `paper_blocked/corporate_action_requires_review` avant toute modification
des positions, du cash, des trades ou de `last_session`. Aucun ratio, prix brut
ou paiement de dividende n'est inventé. Un événement ancien n'est pas rejoué ;
un événement futur ne bloque pas les séances antérieures à sa date.
`corporate_actions_verified=false` et `price_basis_verified=false` restent
explicites. La suppression du blocage exige une entrée ne contenant plus
l'événement problématique dans la période à traiter, sans reset du portefeuille.

Les tests couvrent gaps, priorité du stop, liquidation/halt après redémarrage,
limite de durée sur fenêtre roulante, conservation des anciens trades, frais
cumulés, refus des événements nouveaux/malformés et causalité des filtres.
Le dernier lot ciblé de 36 tests actions/V3/causalité/livraison a réussi.

### Collecte, fraîcheur et limites d'exécution

Le collecteur écrit un statut séparé `research_state/equity_collection.json`.
En cas d'échec, il garde l'ancien bundle comme preuve et le marque inutilisable
pour de nouvelles décisions. Le service poursuit la surveillance crypto
indépendante. Avant d'avancer le portefeuille actions, le worker exige une
collecte réussie vieille de 15 minutes au plus, la même date d'observation dans
le statut et le bundle, et une dernière séance close vieille de 96 heures au
plus. Cette marge tolère les week-ends et jours fériés ordinaires ; elle ne
constitue pas un calendrier officiel. Les rapports cachent les métriques
financières des états bloqués ou périmés et conservent le motif du blocage.

Le papier utilise un signal sur le passé clos puis un achat modélisé à la
clôture de la séance traitée. Ses stops/barrières utilisent des hypothèses sur
la bougie quotidienne. Ce modèle à clôture est déclaré dans `execution_model` ;
il diffère du moteur historique à ouverture suivante et des classes natives
Freqtrade. Une observation après clôture ne prouve pas une exécution courtier
possible au prix de cette clôture.

Yahoo reste la seule source de prix. Les opérations sur titres ne sont pas
recoupées indépendamment, les horaires live sont modélisés à 16h New York et
les suspensions ou séances manquantes propres à un titre ne sont pas certifiées.
L'univers contemporain conserve un biais de survie. Frais, glissement et
liquidité restent des hypothèses ; change, fiscalité et paiements réels ne sont
pas simulés. Les résultats historiques ne satisfont pas les 126 séances futures
du protocole de recherche et n'autorisent aucun ordre réel.

### Conservation au déploiement

Le lot correctif `ad6a836` a été activé sur Oracle. La reprise explicite de la
recherche a ensuite gelé le moteur corrigé sans antidater le nouveau plan.
La vérification avant/après a conservé les cinq plans historiques et leurs
fenêtres consommées, ainsi que les quatre états papier préexistants. Les données
financières n'ont pas été réinitialisées ni les anciens résultats attribués à
la nouvelle révision. Les preuves de cette vérification sont distinctes des
recalculs rétrospectifs ci-dessus.

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

## Cache V3 lié aux véritables données

La recette après déploiement a relevé un second défaut : le cache quotidien
V3 suivait la date et le code, mais pas les données. Le classement public
avait remplacé deux actifs le même jour, tandis que les résultats d'avant
ce remplacement restaient affichés. Le cache exige maintenant l'empreinte
canonique du bundle simulé, en conservant l'ordre des actifs qui influence
l'allocation de cash, et l'identifiant de scope. Le changement d'une barre,
de l'univers ou de son ordre impose un recalcul. Changer seulement la date
de collecte ou les métadonnées de découverte ne suffit pas à le déclencher.
L'ancienne preuve est archivée avant le calcul ; un échec masque les anciens
chiffres plutôt que de les attribuer aux nouvelles données. Cette correction
ne change ni les signaux ni les gels prospectifs enregistrés.

Priorités de recherche restantes : univers prospectif fixé au gel et conservé
malgré les variations du classement courant, validation native Freqtrade des
V3 et coûts stressés explicites avant toute promotion. Une nouvelle liste
courante ne doit pas être confondue avec les observations futures d'un ancien
univers gelé. Les résultats historiques restent séparés et inéligibles.

## Recalcul final sur l'univers renouvelé et preuve Oracle

Le lot de cache `d54f1f33de58` a été activé à 15:43:34 UTC. Le worker
recalcule V3 à 15:43:39 UTC pour le scope
`a43ccbdc2adc41b543f25919f61bac08273c698c6679751964c4063de138f587`,
empreinte données
`c2a2b84a91c8b8de99ae7881823aecfbb90af921dd8895a1f211c192a7cef6f6`.
Cet univers a remplacé UNI/XDG par LTC/ALGO. Les tableaux précédents restent
les preuves du bundle d'avant ce renouvellement, sans réécriture.

| V3 quotidien, univers renouvelé | Rendement | PF | Baisse maximale | Clôtures | Verdict |
|---|---:|---:|---:|---:|---|
| regime_momentum | -1.7321 % | 0.8484 | 5.5394 % | 28 | rejeté |
| triple_barrier | -3.5098 % | 0.7296 | 6.9967 % | 27 | rejeté |
| slow_breakout | -1.1227 % | 0.8427 | 5.7107 % | 14 | rejeté |

À 15:47:55 UTC : les deux conteneurs sont sains, sans redémarrage ; timer
actif, erreurs et alertes vides. Les sept epochs, sept events et zéro fenêtre
consommée sont conservés à l'identique depuis la sauvegarde avant cache ; les
quatre états financiers papier restent inchangés. Les empreintes de moteur
sont identiques à celles du gel, donc cette correction de cache n'impose pas
un nouveau gel prospectif. Deux preuves V3 antérieures sont archivées.

Le rapport périodique suivant, observé à 15:46:41 UTC, a propagé ce recalcul
dans Jarvis sans intervention manuelle. La copie Jarvis est identique au JSON
producteur ; le connecteur renvoie les trois rendements ci-dessus, le témoin
et les trois portefeuilles actions, tous à 100 USD avec zéro transaction.
La crypto cumulée reste 95,8031 EUR, rendement -4,1969 %, seize clôtures ; la
V2 seule compte huit clôtures et -1,5879 EUR réalisés. Aucun signal réel n'est
activé. Le contrôle avec environnement complet réussit 178 tests ; Oracle
réussit aussi la suite de 178 avec quatre dépendances optionnelles ignorées.

Sauvegardes privées : `state-before-reports-20261008T151725Z` puis
`state-before-cache-20261008T153801Z` dans `/home/ubuntu/trading-releases`.
Rollback source du lot final : `previous-20261008T154323Z`.
Archive code final SHA-256 :
`9385df8a464c52bccdc63f032718b17b902ae1fa349bc573f1775d09d6a5e5da`.
