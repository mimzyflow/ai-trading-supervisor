# Résultats actions du 4 octobre 2026

**Bilan : aucune variante retenue pour un raccordement courtier.** Les quatre variantes sont écartées dans les scénarios conservateur et stress. Le scénario sans commission reste exploratoire, parfois positif, avec trop peu de transactions et des arrêts de risque en 2023. Aucun avantage robuste ni résultat prospectif établi.

La collecte et les 72 calculs ont été réalisés sans compte, clé ou ordre courtier. Budget fictif 100 USD, lots entiers, deux allocations de 20 USD. Tous les résultats restent visibles ci-dessous ; aucune règle n’a été modifiée sur leur rendement.

| Fenêtre | Rendements des quatre variantes, conservateur | Clôtures par variante | Cash | Passif même allocation/coûts |
| --- | ---: | ---: | ---: | ---: |
| 2023 | -5.17 à -0.69 % | 1, 2 | 0 % | 19.14 % |
| 2024 | 3.75 % | 1 | 0 % | 3.66 % |
| 2025 | -6.74 à -5.30 % | 2 | 0 % | 9.14 % |
| 2026YTD | 0.00 % | 0 | 0 % | 0.00 % |

En 2026, les variantes ont 1 ou 9 tentatives d’entrée selon leurs règles, mais zéro achat faisable et zéro clôture ; le passif a également zéro titre acheté. Le zéro correspond à du cash resté inutilisé, pas à une performance démontrée. Les prix d’entrée et les lots entiers bloquent les quantités sous le plafond de 20 USD.

Même sans commission, les quatre variantes ont un arrêt de risque en 2023. En 2024, un seul trade par variante ; en 2025, trois ou quatre. Ces observations sont trop rares pour inférer une rentabilité. Les frais individuels, le change et les exécutions effectives d’un courtier restent inconnus. Le passif n’a pas le même arrêt de risque et n’est pas une comparaison à risque égal.

Le drawdown simulé dépasse parfois 5 % (jusqu’à 6,84 % sous stress en 2025) : le seuil déclenche un arrêt modélisé, il ne garantit pas une borne de perte pendant les gaps et après frais.

## Preuves et validation

- Données collectées à `2026-10-04T11:52:43.173762+00:00` : SOFI/U, 1 342 séances par titre du 1er juin 2021 au 2 octobre 2026.
- Couverture et horaires confrontés au calendrier XNYS 4.13.2, avec limites Nasdaq et suspensions propres aux titres explicites. Source unique Yahoo, opérations sur titres non recoupées, biais de survivance : qualité globale non vérifiée.
- Plan fixé à `2026-10-04T11:54:40.884155+00:00` ; protocole versionné avant calcul au commit `5c9d69d`.
- 122 tests réussis sur Python 3.12.14 ; compilation et contrôle de simulation Kraken spot EUR réussis. Revue indépendante des nouveaux modules sans blocage.
- Empreintes des sorties et sources comparées après calcul : identiques. Plan écrit avant réservation de calcul ; nouvelle exécution du même dossier refusée avant simulation.
- Bundle reconstruit exactement avec le collecteur final depuis les réponses originales, sans nouveau téléchargement. Réponses brutes, courbes et transactions restent privées et exclues de Git.
- Les fichiers engine.py, data.py et research.py existants ne changent pas. Le code actif Oracle e01d8ed et sa simulation crypto ne sont pas redéployés par ce lot local.

| Preuve | SHA-256 |
| --- | --- |
| Plan | `7c5ddeaf57eceadf0a0c6ebf667b07ec9936e502e92b539e1651a5f33cb06aaf` |
| Bundle source | `b0f23737ec08fe16142b0290dc175f4f065bffad9d1bf105edda302b5d4f38d4` |
| Bundle volume J-1 | `06eba0e1033a58254f5a90321e65e9f2520af11be3ae12d024dfff86de366c7d` |
| Code de simulation | `86a8001f182af6730591792733bc0ae9c98c4c08764273a0242dc51e7007d2eb` |
| Règles | `9c36bdc416c06f23f43ceddf5a111863f3204cf179f4438c2669b36bfc0234c8` |
| Résultats JSON | `b75bc2b39bb8fbb025cd8ac2178ca4bd187df968c4f6ab8e29a2e1a45f016231` |

Archives locales : `research_results/equity-diagnostics-20261004-v1/` et `research_results/equity-experiment-20261004-v1/`. Le rapport versionné est un résumé calculé de ces sorties, pas un nouveau test. Voir [le protocole](EQUITY_SIMULATIONS.md) pour les sources et les limites.

## Rapport intégral des 72 calculs

### Expérience actions rétrospective

Verdict global : **rejet_experimental**. Aucune sélection de gagnant ni promotion.

Budget fictif : 100 USD, allocation maximale de 20 USD par instrument, lots entiers.
Chaque fenêtre repart de 100. Cash et buy/hold utilisent les mêmes dates, lots et coûts,
sans arrêt de drawdown ; leur risque et leur exposition effective peuvent donc différer.

2023 est le développement descriptif ; 2024, 2025 et 2026YTD sont des tests historiques.
Toutes les périodes sont rétrospectives et exploratoires, sans holdout prospectif.
Les quatre variantes préfixées et les trois scénarios sont publiés intégralement.

Coûts par côté : base 0,1 %, minimum 1, glissement 0,1 % ; stress 0,1 %, minimum 1,
glissement 0,25 %. Zéro commission : hypothèse séparée (frais/minimum 0, glissement 0,1 %).
Ce sont des hypothèses de simulation, aucun tarif courtier vérifié. Fiscalité, change,
garde et frais de financement ne sont pas modélisés.

Univers fixe choisi rétrospectivement : biais de survivance. Qualité déclarée via
research.quality : False, vérification indépendante : False.
La couverture annuelle est contrôlée par nombre de séances et bornes janvier/décembre ;
elle ne certifie pas les calendriers ni toutes les opérations sur titres.

Signaux OHLC inchangés ; décisions sur les clôtures passées, achats à l’ouverture suivante.
Le plafond de liquidité utilise exclusivement le volume de la séance précédente.
La première séance sans antécédent ne peut pas être tradée ; 200 séances de préchauffage
précèdent chaque fenêtre et ne portent aucune transaction. Les stops intrajournaliers
utilisent low et min(stop, ouverture) : approximation sans séquence intraday ni spread réel.
La clôture forcée de fin de fenêtre applique aussi les coûts. Aucun paper trading courtier,
compte, ordre réel, validation réelle ou autorisation de production.

Empreinte du plan : `7c5ddeaf57eceadf0a0c6ebf667b07ec9936e502e92b539e1651a5f33cb06aaf`.
Code : `86a8001f182af6730591792733bc0ae9c98c4c08764273a0242dc51e7007d2eb`.
Bundle original : `b0f23737ec08fe16142b0290dc175f4f065bffad9d1bf105edda302b5d4f38d4`.
Bundle d’exécution (volume J-1) : `06eba0e1033a58254f5a90321e65e9f2520af11be3ae12d024dfff86de366c7d`.

Variantes préfixées (moyenne rapide / lente, fenêtre de breakout) :
- template_0 : 20 / 100 séances, breakout 20 séances ; stop 5 %, durée maximale 60 séances.
- template_1 : 20 / 100 séances, breakout 55 séances ; stop 5 %, durée maximale 60 séances.
- template_2 : 50 / 200 séances, breakout 20 séances ; stop 5 %, durée maximale 60 séances.
- template_3 : 50 / 200 séances, breakout 55 séances ; stop 5 %, durée maximale 60 séances.

## 2023 : 2023-01-03 au 2023-12-29

| Variante | Coûts | Gain net | Rendement | Drawdown | Transactions | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| template_0 | base | -5.166 USD | -5.166 % | 6.204 % | 2 | rejet_experimental |
| template_0 | stress | -5.200 USD | -5.200 % | 6.219 % | 2 | rejet_experimental |
| template_0 | zero_commission_hypothetical | -2.991 USD | -2.991 % | 5.962 % | 3 | rejet_experimental |
| template_1 | base | -5.166 USD | -5.166 % | 6.204 % | 2 | rejet_experimental |
| template_1 | stress | -5.200 USD | -5.200 % | 6.219 % | 2 | rejet_experimental |
| template_1 | zero_commission_hypothetical | -2.991 USD | -2.991 % | 5.962 % | 3 | rejet_experimental |
| template_2 | base | -0.693 USD | -0.693 % | 6.459 % | 1 | rejet_experimental |
| template_2 | stress | -0.742 USD | -0.742 % | 6.484 % | 1 | rejet_experimental |
| template_2 | zero_commission_hypothetical | 1.307 USD | 1.307 % | 5.465 % | 1 | rejet_experimental |
| template_3 | base | -0.693 USD | -0.693 % | 6.459 % | 1 | rejet_experimental |
| template_3 | stress | -0.742 USD | -0.742 % | 6.484 % | 1 | rejet_experimental |
| template_3 | zero_commission_hypothetical | 1.307 USD | 1.307 % | 5.465 % | 1 | rejet_experimental |
| cash | base | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| cash | stress | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| cash | zero_commission_hypothetical | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| buy_hold | base | 19.142 USD | 19.142 % | 15.327 % | 1 | référence |
| buy_hold | stress | 19.054 USD | 19.054 % | 15.331 % | 1 | référence |
| buy_hold | zero_commission_hypothetical | 21.142 USD | 21.142 % | 15.207 % | 1 | référence |

Référence buy/hold base : exposition initiale 18.619 %, cash 80.381 USD, quantités (SOFI : 4, U : 0).
Référence buy/hold stress : exposition initiale 18.647 %, cash 80.353 USD, quantités (SOFI : 4, U : 0).
Référence buy/hold zero_commission_hypothetical : exposition initiale 18.619 %, cash 81.381 USD, quantités (SOFI : 4, U : 0).

## 2024 : 2024-01-02 au 2024-12-31

| Variante | Coûts | Gain net | Rendement | Drawdown | Transactions | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| template_0 | base | 3.755 USD | 3.755 % | 2.349 % | 1 | rejet_experimental |
| template_0 | stress | 3.717 USD | 3.717 % | 2.371 % | 1 | rejet_experimental |
| template_0 | zero_commission_hypothetical | 11.510 USD | 11.510 % | 3.231 % | 1 | rejet_experimental |
| template_1 | base | 3.755 USD | 3.755 % | 2.349 % | 1 | rejet_experimental |
| template_1 | stress | 3.717 USD | 3.717 % | 2.371 % | 1 | rejet_experimental |
| template_1 | zero_commission_hypothetical | 11.510 USD | 11.510 % | 3.231 % | 1 | rejet_experimental |
| template_2 | base | 3.755 USD | 3.755 % | 2.349 % | 1 | rejet_experimental |
| template_2 | stress | 3.717 USD | 3.717 % | 2.371 % | 1 | rejet_experimental |
| template_2 | zero_commission_hypothetical | 11.510 USD | 11.510 % | 3.231 % | 1 | rejet_experimental |
| template_3 | base | 3.755 USD | 3.755 % | 2.349 % | 1 | rejet_experimental |
| template_3 | stress | 3.717 USD | 3.717 % | 2.371 % | 1 | rejet_experimental |
| template_3 | zero_commission_hypothetical | 11.510 USD | 11.510 % | 3.231 % | 1 | rejet_experimental |
| cash | base | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| cash | stress | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| cash | zero_commission_hypothetical | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| buy_hold | base | 3.665 USD | 3.665 % | 4.400 % | 1 | référence |
| buy_hold | stress | 3.627 USD | 3.627 % | 4.414 % | 1 | référence |
| buy_hold | zero_commission_hypothetical | 11.330 USD | 11.330 % | 6.799 % | 1 | référence |

Référence buy/hold base : exposition initiale 9.720 %, cash 89.280 USD, quantités (SOFI : 1, U : 0).
Référence buy/hold stress : exposition initiale 9.734 %, cash 89.266 USD, quantités (SOFI : 1, U : 0).
Référence buy/hold zero_commission_hypothetical : exposition initiale 19.439 %, cash 80.561 USD, quantités (SOFI : 2, U : 0).

## 2025 : 2025-01-02 au 2025-12-31

| Variante | Coûts | Gain net | Rendement | Drawdown | Transactions | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| template_0 | base | -6.673 USD | -6.673 % | 6.673 % | 2 | rejet_experimental |
| template_0 | stress | -6.768 USD | -6.768 % | 6.768 % | 2 | rejet_experimental |
| template_0 | zero_commission_hypothetical | 8.485 USD | 8.485 % | 3.716 % | 4 | rejet_experimental |
| template_1 | base | -6.673 USD | -6.673 % | 6.673 % | 2 | rejet_experimental |
| template_1 | stress | -6.768 USD | -6.768 % | 6.768 % | 2 | rejet_experimental |
| template_1 | zero_commission_hypothetical | 8.485 USD | 8.485 % | 3.716 % | 4 | rejet_experimental |
| template_2 | base | -5.301 USD | -5.301 % | 5.301 % | 2 | rejet_experimental |
| template_2 | stress | -5.393 USD | -5.393 % | 5.393 % | 2 | rejet_experimental |
| template_2 | zero_commission_hypothetical | 8.568 USD | 8.568 % | 3.633 % | 4 | rejet_experimental |
| template_3 | base | -6.740 USD | -6.740 % | 6.740 % | 2 | rejet_experimental |
| template_3 | stress | -6.836 USD | -6.836 % | 6.836 % | 2 | rejet_experimental |
| template_3 | zero_commission_hypothetical | 9.243 USD | 9.243 % | 2.958 % | 3 | rejet_experimental |
| cash | base | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| cash | stress | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| cash | zero_commission_hypothetical | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| buy_hold | base | 9.139 USD | 9.139 % | 8.362 % | 1 | référence |
| buy_hold | stress | 9.077 USD | 9.077 % | 8.363 % | 1 | référence |
| buy_hold | zero_commission_hypothetical | 11.139 USD | 11.139 % | 8.280 % | 1 | référence |

Référence buy/hold base : exposition initiale 15.015 %, cash 83.985 USD, quantités (SOFI : 1, U : 0).
Référence buy/hold stress : exposition initiale 15.037 %, cash 83.963 USD, quantités (SOFI : 1, U : 0).
Référence buy/hold zero_commission_hypothetical : exposition initiale 15.015 %, cash 84.985 USD, quantités (SOFI : 1, U : 0).

## 2026YTD : 2026-01-02 au 2026-10-02

| Variante | Coûts | Gain net | Rendement | Drawdown | Transactions | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| template_0 | base | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_0 | stress | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_0 | zero_commission_hypothetical | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_1 | base | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_1 | stress | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_1 | zero_commission_hypothetical | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_2 | base | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_2 | stress | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_2 | zero_commission_hypothetical | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_3 | base | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_3 | stress | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| template_3 | zero_commission_hypothetical | 0.000 USD | 0.000 % | 0.000 % | 0 | rejet_experimental |
| cash | base | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| cash | stress | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| cash | zero_commission_hypothetical | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| buy_hold | base | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| buy_hold | stress | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |
| buy_hold | zero_commission_hypothetical | 0.000 USD | 0.000 % | 0.000 % | 0 | référence |

Référence buy/hold base : exposition initiale 0.000 %, cash 100.000 USD, quantités (SOFI : 0, U : 0).
Référence buy/hold stress : exposition initiale 0.000 %, cash 100.000 USD, quantités (SOFI : 0, U : 0).
Référence buy/hold zero_commission_hypothetical : exposition initiale 0.000 %, cash 100.000 USD, quantités (SOFI : 0, U : 0).

Les transactions absentes et quantités nulles restent visibles dans les références.
Courbes et transactions détaillées : curves.json/CSV et trades.json/CSV, fichiers privés.
