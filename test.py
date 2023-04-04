import signal 
import time   

Sentry = 0

# Create a Signal Handler for Signals.SIGINT:  CTRL + C 
def SignalHandler_SIGINT(SignalNumber,Frame):
    global Sentry 
    Sentry += 1

signal.signal(signal.SIGINT,SignalHandler_SIGINT) 

while Sentry < 3: #exit loop when Sentry = False
    print('Long continous event Eg,Read from sensor')
    time.sleep(1)

print('Out of the while loop')
print('Clean up code Here')