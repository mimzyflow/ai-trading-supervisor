# Simulations actions sans compte courtier

## Protocole fixé avant calcul, 4 octobre 2026

Moussa autorise des essais sans compte financier ni argent réel pendant que
l'accès API et papier aux actions Kraken reste à confirmer. Le laboratoire
local est indépendant de Kraken et d'Alpaca. Aucun compte, clé ou ordre courtier
n'est nécessaire pour ces essais. Un éventuel raccordement reste une étape
ultérieure, après lecture des preuves et validation humaine.

### Périmètre et données

- Univers exploratoire fixé : `SOFI` et `U`, en USD, du 1er juin 2021 au
  2 octobre 2026 inclus. Ces deux titres servent à tester le moteur ; ce ne
  sont pas des recommandations d'achat ni une sélection de titres gagnants.
- Choix motivé par un historique public commun après la cotation de SoFi,
  et l'absence de dividendes déclarée dans leurs rapports annuels 2025. Ce
  choix contemporain contient un biais de survivance et ne représente pas
  un univers historique complet ou un portefeuille diversifié.
- Données publiques Yahoo Finance en lecture seule, réponses originales et
  empreintes conservées dans `research_results/`, exclu de Git. Aucun prix,
  volume ou séance manquant n'est interpolé. Réponse invalide ou incomplète :
  expérience refusée.
- Les cours Yahoo sont ajustés pour les splits. Le premier collecteur accepte
  uniquement une période sans split, dividende ni distribution annoncés dans
  la réponse. Tout événement exige une autre source et une revue ; il ne
  fabrique ni prix bruts ni date de paiement.
- Horaires et présence des séances confrontés au calendrier logiciel XNYS,
  avec changement d'heure et fermetures anticipées. Nasdaq et NYSE partagent
  ici le calendrier des séances régulières ; cela ne vérifie pas chaque
  suspension propre à un titre. La source unique et l'absence d'événement
  annoncé ne constituent pas une vérification indépendante des cours et
  opérations sur titres. `corporate_actions_verified=false` et
  `historical_universe_verified=false` restent explicites.

### Règles et périodes

Les quatre variantes `TEMPLATES` existantes sont conservées : moyennes simples
20/100 ou 50/200 séances, breakout 20 ou 55 séances, stop de position à 5 %,
durée maximale de 60 séances. Aucune optimisation supplémentaire ni sélection
du meilleur titre après lecture des résultats.

| Fenêtre | Rôle | Calcul |
| --- | --- | --- |
| 2023 | Développement descriptif | Toutes les variantes |
| 2024 | Test historique avec règles fixées | Toutes les variantes |
| 2025 | Test historique avec règles fixées | Toutes les variantes |
| 2026 jusqu'au 2 octobre | Test historique partiel | Toutes les variantes |

Toutes ces fenêtres restent rétrospectives. Elles ne sont pas les 126 séances
prospectives exigées par la recherche existante et ne peuvent pas devenir un
contrôle futur après leur consultation. Les séances antérieures initialisent
les indicateurs ; chaque fenêtre démarre sans position et sans résultat antérieur.
Les années pleines doivent être présentes et les indicateurs doivent disposer
d'au moins 200 séances de préchauffage.

### Budget, exécution et coûts

Capital fictif initial de 100 USD, allocation maximale de 20 USD par titre,
deux positions au plus, actions entières, sans levier ni ventes à découvert.
Les règles du connecteur papier et de la simulation crypto ne sont pas modifiées.
Un titre trop cher peut produire zéro ordre ; ce constat doit être publié.

| Scénario hypothétique | Frais proportionnels par côté | Minimum par ordre | Glissement par côté |
| --- | --- | --- | --- |
| Conservateur existant | 0,10 % | 1 USD | 0,10 % |
| Stress | 0,10 % | 1 USD | 0,25 % |
| Sans commission | 0 % | 0 USD | 0,10 % |

Ces hypothèses ne sont pas un devis Kraken, Alpaca ou IBKR. Le scénario sans
commission reste un diagnostic séparé ; il n'autorise pas à choisir le scénario
qui donne le meilleur rendement. FX, fiscalité et rendement des liquidités ne
sont pas modélisés. Le cash fictif a un rendement de zéro.

Signal sur clôtures déjà connues, exécution modélisée à l'ouverture suivante.
Le plafond de participation utilise le volume de la séance précédente, jamais
le volume futur du jour d'achat. La copie dérivée de calcul possède sa propre
empreinte ; le bundle source est conservé. Un stop touché dans une bougie
quotidienne est une hypothèse d'exécution, pas une preuve de liquidité au seuil.
Les gaps et les coûts peuvent dépasser le seuil d'arrêt de portefeuille de 5 %.

### Comparaisons et conclusion

Chaque variante est comparée au cash et à un achat-conservation sur la même
fenêtre, avec les mêmes lots, allocations et coûts. Le passif n'utilise pas
l'arrêt de risque, et l'allocation égale n'égalise pas les risques ou l'exposition
réellement obtenue. Gains nets, nombre de clôtures, profit factor, baisse maximale,
ordres faisables et arrêts sont publiés ensemble. Les courbes et les transactions
permettent une relecture des résultats agrégés.

Le plan et ses empreintes sont écrits avant le premier calcul dans un dossier
neuf. Les résultats ne sont jamais écrasés. Un changement de données, de code
ou de règle doit conserver l'ancien essai et être déclaré comme nouvelle
expérience. Un résultat positif, un faible nombre d'ordres ou zéro ordre ne
valident jamais le bot. Le verdict reste exploratoire, inconclusif ou un rejet
expérimental selon les observations. `real_money_eligible=false` est permanent.

## Sources et limites des services

- [SoFi, rapport annuel 2025](https://www.sec.gov/Archives/edgar/data/1818874/000181887426000013/sofi-20251231.htm) : politique de dividendes.
- [Unity, rapport annuel 2025](https://www.sec.gov/Archives/edgar/data/1810806/000181080626000011/unity-20251231.htm) : cotation et politique de dividendes.
- [Yahoo Finance, définition des prix historiques](https://finance.yahoo.com/quote/%5EGSPC/history/?p=%5EGSPC) : clôture ajustée pour les splits, clôture ajustée supplémentaire pour les distributions.
- [Calendriers logiciels exchange_calendars](https://github.com/gerrymanoim/exchange_calendars) : calendrier et horaires modélisés, pas source de prix.
- [Alpaca Paper](https://docs.alpaca.markets/us/docs/paper-trading) : nécessite un compte et des clés pour sa simulation API. Le présent essai n'est pas une recette Alpaca.
- [Kraken, actions classiques](https://support.kraken.com/articles/getting-started-with-equities) : disponibilité commerciale, sans confirmation ici d'une API ou d'un environnement papier.

## Résultats

Le premier essai effectif est terminé : 1 342 séances par titre, 72 calculs,
quatre variantes écartées dans les scénarios conservateur et stress. La source
unique et les transactions trop rares empêchent une validation financière,
même lorsque le scénario sans commission est positif. Aucun compte à créer
sur la base de ces seuls résultats. Voir le [rapport complet du 4 octobre](EQUITY_SIMULATION_RESULTS_2026-10-04.md).

Cette section est ajoutée après calcul. Le protocole ci-dessus était déjà
versionné au commit `5c9d69d` avant toute performance calculée.
