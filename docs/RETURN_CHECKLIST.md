# Reprise avec Moussa : actions/ETF et publication des rapports

La simulation crypto et la recherche quotidienne continuent sur Oracle. Ce
document distingue les décisions/connexions de Moussa des travaux techniques
qui restent à faire après ces prérequis. Il ne dit pas que le bot actions/ETF
ou la chaîne prospective sont déjà opérationnels.

## Intervention de Moussa

1. **Examiner Kraken en premier**, conformément à la préférence de Moussa.
   Voir [`KRAKEN_ACTIONS_FEASIBILITY.md`](KRAKEN_ACTIONS_FEASIBILITY.md), sources
   officielles consultées le 4 octobre 2026. Les xStocks EEE sont accessibles
   sous conditions via fiat/Convert, mais pas par carnet/API. Les actions
   classiques sont officiellement disponibles aux clients français éligibles
   via Kraken Pro web/app et l'app Kraken, pas `kraken.com/c`. Connexion et
   consultation `Marchés > Actions` vérifiées ; formulaire Kraken Stocks ouvert,
   demande technique préparée, envoi laissé à Moussa. Un éventuel questionnaire
   ou accord reste à sa main. Aucune activation ou transaction nouvelle effectuée.
   Leur API et leur mode papier utiles au bot restent à confirmer pour son
   compte. Aucun identifiant API n'est
   demandé avant cette confirmation. Alpaca ne remplace pas automatiquement
   Kraken : si la voie est indisponible, Moussa choisit recherche locale sans
   ordre ou examen explicite d'un autre courtier papier.
2. **Choisir le périmètre actions/ETF** après cette vérification : un ou deux
   instruments précisément identifiés, leur produit et leur devise. Actions
   classiques, xStocks et ETF UCITS ne sont pas interchangeables. L'adaptateur
   Alpaca Paper préparé couvre des titres US si cette option est retenue.
3. **Se connecter ou créer un compte papier dédié**, uniquement après
   confirmation d'une voie papier utile et choix du périmètre/courtier,
   gérer email/MFA et consentements. Aucun compte live ni dépôt n'est requis
   pour préparer cette simulation. Si Alpaca est explicitement retenu, choisir
   **100 USD virtuels**, distincts des **100 EUR virtuels** de Kraken ; aucune
   conversion EUR/USD n'est supposée. Le solde par défaut de 100 000 USD ne
   passe pas notre contrôle initial. Le tableau de bord permet de créer un
   nouveau compte papier ; conserver tout compte/historique existant.
4. **Générer les identifiants API papier de la voie confirmée**, puis les
   installer en privé. Ne jamais les mettre dans le chat, Notion, Git ou une
   capture. Le contrôle Alpaca préparé attend, seulement si Alpaca est choisi,
   `ALPACA_PAPER_KEY_ID` et
   `ALPACA_PAPER_SECRET_KEY` ; aucun fichier de secrets n'est recherché.
   Il ne peut utiliser aucune clé live ou Kraken.
5. **Publication GitHub facultative** : créer un jeton dédié à ce seul dépôt,
   avec accès aux issues en écriture et expiration, puis l'installer dans
   l'environnement privé Oracle. Le connecteur disponible ne fournit pas de
   fonction de création de jeton. La simulation fonctionne sans ce jeton ;
   seuls les envois automatiques vers le ticket de statut en dépendent.

Ces étapes demandent ses choix ou sa session de compte ; elles ne demandent
pas toutes d'être physiquement devant le Mac. Aucune demande de clé par message.

## Travaux techniques que Codex peut reprendre ensuite

Le laboratoire sans compte est désormais exécuté : collecte publique SOFI/U,
1 342 séances par titre et 72 simulations historiques. Les quatre variantes
restent écartées sous les coûts conservateurs ; le scénario sans commission
reste exploratoire et trop peu fourni. Voir `EQUITY_SIMULATIONS.md` et
`EQUITY_SIMULATION_RESULTS_2026-10-04.md`. Aucun compte supplémentaire demandé
pour ce lot. Ces calculs ne sont ni une recette Alpaca ni les 126 séances futures.

- Si Alpaca est explicitement retenu, lancer `scripts/check_paper_readiness.py` :
  uniquement GET, hôte papier fixé,
  compte actif/non bloqué, monnaie USD, cash et equity égaux aux 100 USD initiaux,
  zéro position et ordre en attente, un ou deux instruments autorisés/tradables.
  Le marché peut être fermé pendant ce contrôle. Le résultat ne prouve pas la
  disponibilité d'une stratégie, d'un historique ou d'exécutions.
- Vérifier les données réellement disponibles et leurs conditions d'utilisation,
  les séances, les prix bruts, les splits/dividendes et les tailles de lots.
  Un résultat négatif ou zéro ordre faisable est une issue acceptable.
- Implémenter et raccorder l'exécuteur prospectif au périmètre retenu : signaux
  figés avant exécution, état persistant, ordres uniques, reprise sur timeout,
  exécutions partielles, frais et rapprochement portefeuille/ordres/exécutions.
  **Cet exécuteur et son registre de preuves ne sont pas encore implémentés.**
- Effectuer une recette papier de bout en bout sur les vrais accès, y compris
  indisponibilités et reprises. Les tests actuels du connecteur restent des tests
  avec réponses simulées ; aucun ordre courtier n'a été envoyé.
- Collecter le registre prospectif vérifiable avant toute validation du parent
  ou création d'un descendant. Le drapeau `verified_forward` d'un fichier JSON
  ne constitue pas, seul, une preuve indépendante. La fabrique reste inactive.
- Une fois le jeton dédié fourni, tester l'envoi et la relecture d'un rapport
  récent dans l'issue. Jusqu'à cette recette, publication automatique non validée.

## Ce qui demande du temps ou une décision distincte

- Aucune variante crypto ne passe actuellement le développement. Une candidate
  admissible doit être gelée avant 126 nouvelles séances, puis satisfaire les
  filtres et une observation prospective. On ne peut pas remplacer ce délai
  par une optimisation répétée du même historique.
- L'argent réel reste désactivé. Un futur passage au réel exige des résultats
  examinés et une décision explicite de Moussa ; ce n'est pas une étape à
  terminer automatiquement au retour.
- n8n reste reporté selon la décision antérieure ; sa connexion est un chantier
  distinct à reprendre après validation de la stratégie.

## Contrôle Alpaca préparé, si cette voie est choisie

```sh
python3 scripts/check_paper_readiness.py
```

Sans identifiants et univers explicites, le programme répond `awaiting_setup`,
ne contacte pas le courtier et sort avec le code 2. Un succès donne
`initial_setup_ready` mais conserve `broker_orders_activated=false`,
`strategy_validated=false` et `real_money_eligible=false`.

Sources officielles consultées le 3 octobre 2026 :

- [Alpaca Paper : compte papier, solde initial et nouveau compte](https://docs.alpaca.markets/us/docs/paper-trading)
- [Alpaca Account : devise, cash, equity et blocages](https://docs.alpaca.markets/us/docs/account-plans)
- [Alpaca GET account, hôte papier](https://docs.alpaca.markets/us/reference/getaccount-1)

Analyse Kraken et sources actualisées le 4 octobre 2026 :
[`KRAKEN_ACTIONS_FEASIBILITY.md`](KRAKEN_ACTIONS_FEASIBILITY.md).
