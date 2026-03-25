Interface utilisateur de la fonction de calibration
1) Ajouter une section Calibration dans la fenêtre principale, qui regroupe tous les éléments liés à la calibration.
2) Permettre à l’utilisateur d’entrer :
- le nombre de masses de calibration à utiliser ;
- le nombre de bits de l’ADC.
Ces valeurs doivent rester affichées dans l’interface.
3) Ajouter un bouton Lancer la calibration.
4) Lorsqu’on lance la calibration, ouvrir une nouvelle fenêtre dédiée.
5) Dans cette fenêtre, afficher :
- le numéro de la masse actuelle ;
- un champ permettant à l’utilisateur d’entrer la valeur réelle de la masse.
6) Dans la fenêtre de calibration, ajouter trois boutons :
- Next : passer à la masse suivante ;
- Previous : revenir à la masse précédente ;
- Stop : arrêter la calibration.
7) Lorsqu’on appuie sur Next, la valeur mesurée pour la masse courante est enregistrée, puis on passe à la masse suivante.
8) Lorsqu’on appuie sur Previous, la mesure de la masse précédente doit être refaite.
9) Lorsqu’on arrive à la dernière masse de calibration, le bouton Next devient End.
En appuyant sur End, on termine la calibration, on ferme la fenêtre, et la fonction de calibration retourne les valeurs de courant mesurées pour chaque masse.
10) De retour dans la fenêtre principale, la section Calibration doit afficher, pour chaque masse :
son numéro ;
- sa masse réelle ;
- la valeur de courant mesurée.


Logique de la fonction de calibration
1) Utiliser la valeur de référence courantRef, obtenue lors du tare de calibration au tout début. Cette valeur représente le zéro.
2) Démarrer la fonction de calibration lorsque l’utilisateur appuie sur le bouton prévu dans l’interface.
3) Pour chaque masse de calibration, accumuler la valeur numérique lue par le capteur de courant de l’Arduino.
La valeur retenue pour une masse est celle confirmée lorsque l’utilisateur appuie sur Next.
4) Si l’utilisateur appuie sur Previous, la mesure précédente est annulée et doit être refaite.
5) Lorsque l’interface indique que la calibration est terminée :
- soustraire la valeur de référence courantRef à chaque mesure ;
- convertir les valeurs numériques en ampères.
Le nombre de bits de l’ADC est fourni par l’utilisateur, et la plage de lecture du courant est de -1.5 A à 1.5 A.
6) Conserver les valeurs numériques mesurées pendant la calibration afin de pouvoir les réutiliser plus tard pour linéariser les mesures de masse.