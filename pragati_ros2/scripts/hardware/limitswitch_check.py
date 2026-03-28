
import rospy
import time
import pigpio
from gpiozero import Button,LED,AngularServo
from gpiozero import PWMLED



#gpiozero is the library which available in rpi for accessing the io pins, refer the documents for more info " https://gpiozero.readthedocs.io/en/stable/api_input.html"
from time import sleep
from std_msgs.msg import Bool
from std_msgs.msg import String
from std_srvs.srv import SetBool
from std_msgs.msg import Float32

OFF = 0
ON  = 1

CLK = 1       #clock wise direction
ANTI_CLK = 0  #anti clock wise_direction
last_data_vaccum = False

pi = pigpio.pi()
#pi.set_pull_up_down(2,pigpio.PUD_UP)
#pi.set_pull_up_down(3,pigpio.PUD_UP)
#pi.set_pull_up_down(5,pigpio.PUD_UP)
pi.set_pull_up_down(26,pigpio.PUD_DOWN)


limit_switch_list = [0,0,Button(2,pull_up=True),Button(3,pull_up=True),Button(16,pull_up=True),Button(26,pull_up=True)]#23,14,18,6 gpio pin of the rpi



#limit_switch_list = [0,0,Button(2,pull_up = True),Button(3,pull_up = True),Button(5,pull_up = True),Button(26,pull_up = True)]

# refer to the gpio pin diagram of the rpi, we have to connect the other end of the switch to ground
#here we are making the servo into off position by assinging the  pin and pwm width

#here we are gonna define the motor pins ( pins for the cytron controller)
# we need 8 pins 4 pwm and 4 enable pins
#motor_1_direction PWMLED   #the pwm value ranges from 0.0 to 1
#9 5 13 26
#servo = AngularServo(18, min_angle=-180, max_angle=180)
#here we have defined all the limitswithes and assigned them to the corresponding io in rpi
#this funcion is gonna publish the status of the limit swithc //whether it can be a single time publisher or not has to be checked

     # if req.joint_id >=2 and req.joint_id<=5:
if limit_switch_list[2].is_pressed:
     print("button 2 is pressed")
else:
     print("button 2 is not pressed")

# if req.joint_id >=2 and req.joint_id<=5:
if limit_switch_list[3].is_pressed:
     print("button 3 is pressed")

else:
     print("button 3 is not pressed")

       # if req.joint_id >=2 and req.joint_id<=5:
if limit_switch_list[4].is_pressed:
     print("button 5 is pressed")

else:
     print("button 5 is not pressed")

      # if req.joint_id >=2 and req.joint_id<=5:
if limit_switch_list[5].is_pressed:
     print("button 26 is pressed")

else:
     print("button 26 is not pressed")


