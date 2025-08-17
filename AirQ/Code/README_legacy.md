
# ![alt text](https://actua-urv.cat/wp-content/uploads/2021/05/cropped-actua-fons-blanc-petit.png)

ACTUA estudia la transmissió del virus de la COVID-19 en escoles d’educació infantil i primària, particularment dintre de les aules, i ho fa cercant a través de sensors situats a l’aula la correlació entre paràmetres mesurables i el risc de contagi. La transmissió en les escoles podria empitjorar a mesura que s’entri a l’hivern i més enllà, i també a mesura que el virus evolucioni.

Web: <https://actua-urv.cat/el-projecte/>

## Arquitectura
![alt text](https://i.ibb.co/ZHRty8W/Arquitectura-ACTUA.png)

## Explicació

Codi programat en Python desenvolupat per el projecte ACTUA de la URV. L'objectiu d'aquest codi es la recol·lecció de dades de diferents sensors per poder barrejar les dades amb dades de contagis de la COVID-19. EL codi està desenvolupat plenament per funcionar en una Raspberry Pi

El projecte s'estructura en diferents directoris.
- **config**: Fitxers de configuració, són els únics fitxers que s'han de modificar per a que els programes puguin funcionar
- **utils**: Fitxers en *Python* responsables de coordinar diferents tasques del sistema: Bases de dades, gestió de variables, procés de crides a la API...
- **sensors**: Codi dels sensors. Poden funcionar amb varies tecnologies... GPIO pins, Bluetooth...
- **logs**: sistema de logs on es pot veure el funcionament del programa: 
```bash
 tail -n 50 logs/app.log
```
- **exports**: Fitxers csv amb la informació dels sensors per enviar al servidor.
- **db**: Fitxers locals de la base de dades en que es guarda temporalment les dades dels diferents sensors. 


## Utilització

- **Inici:**
```bash
cd /home/pi/ACTUA
./start.sh
```
- **Parar:**
```bash
cd /home/pi/ACTUA
./stop.sh
```
- **Comprovar el funcionament:**
```bash
cd /home/pi/ACTUA
./check.sh
```
El codi es pot executar directament amb un crontab, fent que al arrancar la RPi4 el codi s'executi automàticament.
## Autors
- Edgar Batista
- Oriol Villanova