from src import bot, bot_token

if __name__ == '__main__':
    bot.run(bot_token)


#TODO! if people start using it, auto-delete from diagon-alley


#TODO! sprout:
# trigger on herbology related stuff:
# - weekly plants,
# - own timers for plants with notification for the server:
# -- for own timers use create_a_task that is run on restart of the bot:
# create_a_task(timer={"hours":0, "minutes":0, "seconds":0}).start(event_info={"id": 1})

# -- the times are from the database. while creating save to database. after executing delete
# -- limit for user that is set in code (2 for testing)
# -- seperate into aquatic and non aquatic


## CRAZY IDEAS ##

#TODO! subscription system:
# - pick a subscription and add the role to members before the event
# - clear all subscriptions on another button
# - IMPORTANT: check if clearing the role keeps the notification!

#TODO! image host:
# - upload file to the server, store only part of the link in db
# - replace old files on image host
# - show all filenames
# - delete file if removed from db

#TODO! a queue for all events this day so if the bot restarts he knows if he has to send something
# - when they trigger normally just remove them

#TODO! portkey:
# - automatic add to a paste service

#TODO! db changes:
# - insert without defaults if provided
# - more backups?
# - update multiple, instead of just one?
# - multiple primary keys?