Interface utilisateur de la fonction de calibration (Coder dans le fichier ui.py)
1) Ajouter une section Calibration dans la fenêtre principale, qui regroupe tous les éléments liés à la calibration.
2) Permettre à l’utilisateur d’entrer (peut être entré manuellement, ou incrementé/décrément avec la mollette de la souris) :
- le nombre de masses de calibration à utiliser ;
- le nombre de bits de l’ADC.
- le temps de moyennage en milisecondes (minimum 1000 ms).
Ces valeurs doivent rester affichées dans l’interface.
3) Ajouter un bouton Lancer la calibration.
4) Lorsqu’on lance la calibration, ouvrir une nouvelle fenêtre dédiée.
5) Dans cette fenêtre, afficher :
- le numéro de la masse actuelle ;
- un champ permettant à l’utilisateur d’entrer la valeur réelle de la masse.
6) Dans la fenêtre de calibration, ajouter trois boutons et une boite à cocher :
- Next : passer à la masse suivante ;
- Previous : revenir à la masse précédente ;
- Stop : arrêter la calibration.
- Boite à cocher : Nouvelle masse déposée sur le plateau.
7) La boite envoie le signal à la fonction de calibration pour lui dire qu'elle peut commencer son traitement
8) Lorsqu’on appuie sur Next (si le bool nextMasse == True), la valeur mesurée pour la masse courante est enregistrée, puis on passe à la masse suivante et on met bool nextMasse == False.
9) Lorsqu’on appuie sur Previous, la mesure de la masse précédente doit être refaite. Ce bouton peut être appuyé n'importe quand, toutefois il dois mettre bool nextMasse == False.
10) Lorsqu’on arrive à la dernière masse de calibration, le bouton Next devient End.
En appuyant sur End, on termine la calibration, on ferme la fenêtre, et la fonction de calibration retourne les valeurs de courant mesurées pour chaque masse.
11) De retour dans la fenêtre principale, la section Calibration doit afficher, pour chaque masse :
son numéro ;
- sa masse réelle ;
- la valeur de courant mesurée en tension.


Logique de la fonction de calibration (coder dans le fichier masse.py)
1) Utiliser la valeur de référence courantRef, obtenue lors du tare de calibration au tout début. Cette valeur représente le zéro.
2) Démarrer la fonction de calibration lorsque l’utilisateur appuie sur le bouton prévu dans l’interface.
3) Lorsque la boite à cocher est fait, on appel la fonction nextMasse.
4) Pour chaque masse de calibration, accumuler la valeur numérique lue par le capteur de courant de l’Arduino.
La valeur retenue pour une masse est celle retourné par la fonction nextMasse. Le bouton NEXT est actif seulement si bool nextMasse == True.
5) Si l’utilisateur appuie sur Previous, la mesure précédente est annulée et doit être refaite.
6) Lorsque l’interface indique que la calibration est terminée :
- soustraire la valeur de référence courantRef à chaque mesure ;
- convertir les valeurs numériques en tension (car le capteur de courant nous donne une tension lue par l'ADC).
Le nombre de bits de l’ADC est fourni par l’utilisateur, et la plage de lecture de tension est de -2 V à 2 V.
7) Conserver les valeurs en tension mesurées pendant la calibration afin de pouvoir les réutiliser plus tard pour linéariser les mesures de masse.
Utiliser un dictionnaire, dont la clef est la masse de calibration et la valeur est la tension mesurée.


Logique de la fonction nextMasse (coder dans le fichier masse.py)
1) Vérifie que l'asservissement de la balance est fait et que la position de la balance est revenue à positionRef en régime permanent. Cette valeur est obtenue par le capteur de position.
2) Une fois la balance en régime permanent, on attend le délai du temps de moyennage. Après ça, la valeur bool nextMasse devient True et le bouton NEXT devient utilisable.
3) La valeur mesuré est la moyenne des données envoyer par l'Arduino entre le moment ou l'asservissement stable et le délai de moyennage, au minimum. Sinon, la valeur mesuré est la moyenne jusqu'au moment ou l'utilisateur appuie sur NEXT.
4) Retourne la valeur mesurée
