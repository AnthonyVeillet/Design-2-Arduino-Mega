======== Interface utilisateur de la fonction de calibration (Coder dans le fichier ui.py) ========
1) Ajouter une section Calibration dans la fenêtre principale, qui regroupe tous les éléments liés à la calibration.
2) Permettre à l’utilisateur d’entrer (peut être entré manuellement, ou incrementé/décrément avec la mollette de la souris) :
    - le nombre de masses de calibration à utiliser (minimum 3) ;
    - le temps de moyennage en milisecondes (minimum 1000 ms).
    - Et on affiche que c'est un ADC 10 bits.
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
10) Lorsqu’on arrive à la dernière masse de calibration, le bouton Next devient End. En appuyant sur End, on termine la calibration, on ferme la fenêtre, et la fonction de calibration retourne les valeurs de courant mesurées pour chaque masse.
11) De retour dans la fenêtre principale, la section Calibration doit afficher, pour chaque masse :
    - son numéro ;
    - sa masse réelle ;
    - la valeur de courant mesurée en tension.
    - afficher cette courbe dans un graphique à leur droite, où l'axe x est la Tension (V) et l'axe y la Masse (g).


======== Logique de la fonction de calibration (coder dans le fichier masse.py) ========
1) Démarrer la fonction de calibration lorsque l’utilisateur appuie sur le bouton prévu dans l’interface de la fenêtre originale.
2) Lorsque la boite à cocher (dans la seconde fenetre de calibration) est activée, on appel la fonction nextMasse.
3) Pour chaque masse de calibration, accumuler la valeur retourné par la fonction nextMasse.
4) Si l’utilisateur appuie sur Previous, la mesure précédente est annulée et doit être refaite.
5) Lorsque l’interface ui indique que la calibration est terminée :
    - convertir les valeurs numériques en tension (car le capteur de courant nous donne une tension lue par l'ADC 10 bits). La plage de lecture de tension est de 0 V à 5 V.
6) Conserver les valeurs en tension mesurées pendant la calibration afin de pouvoir les réutiliser plus tard pour linéariser les mesures de masse. Utiliser un dictionnaire, dont la clef est la masse de calibration et la valeur est la tension mesurée. Enregistrer ce dictionnaire dans un fichier calibration.


======== Logique de la fonction nextMasse (coder dans le fichier masse.py) ========
1) Vérifie que l'asservissement de la balance est fait, soit lorsque la variable bool flag == True.
2) Une fois la balance en régime permanent, on attend le délai du temps de moyennage. Après ce délai, la valeur bool nextMasse devient True et le bouton NEXT du Ui devient utilisable.
3) La valeur mesuré curMoyen est obtenue par la moyenne des données envoyer par l'Arduino entre le moment ou flag == True et la fin du délai de moyennage, au minimum. Sinon, la valeur mesuré est la moyenne jusqu'au moment ou l'utilisateur appuie sur NEXT. Cette valeur est obtenue par la variable temps réel cur se trouvant dans le fichier ui.py. Elle change automatique en temps réel, il faut donc faire la moyenne de toutes ses valeurs.
4) Retourne la valeur mesurée curMoyen


======== Logique de la fonction iterpolation (coder dans le fichier masse.py) ========
TODO


======== Logique de la fonction convert_to_masse (coder dans le fichier masse.py) ========
TODO