# Cycle de recherche 02 h — 3 octobre 2026

## Contrôle de robustesse

Le test `MoussaSmallCapMomentum` reste non validé malgré +7,06 % sur ~83 jours.
La fenêtre développement perd -1,54 % (PF 0,63), tandis que la validation gagne
+8,60 % (PF 1,65). Le P/L global reste en outre dominé à ~85 % par ARB/EUR.

## Filtre de liquidité / spread

L'univers dynamique contient des actifs plus petits mais encore liquides. Le contrôle
des spreads confirme qu'un filtre d'exécution est indispensable : plusieurs actifs
ont 10-22 bps de spread observé, tandis que certains descendent sous 5 bps.
Le prochain protocole ne doit donc pas assimiler « petite capitalisation » à
« microcap » et doit conserver volume minimal + plafond de spread.

## Décision

Candidate rejetée comme stratégie robuste à ce stade. Aucun changement du bot Oracle,
aucune activation réelle, aucun dépôt et aucune modification n8n.

## Prochaine expérience

1. Leave-one-pair-out, en commençant par retirer ARB/EUR.
2. Sensibilité des coûts à 0,8 %, puis scénario plus pénalisant.
3. Tester un filtre de régime de marché sans optimiser sur la fenêtre de validation.
4. Exiger profit factor > 1 sur développement ET validation.
5. Refuser toute candidate dont une paire explique une part dominante du P/L.