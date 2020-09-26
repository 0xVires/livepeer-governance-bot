import requests
import json
from config_private import TEL_URL, DISCORD_HOOK_ID, DISCORD_HOOK_TOKEN
from discord import Webhook, RequestsWebhookAdapter

def get_totalActiveStake():
    GRAPH_URL = 'https://api.thegraph.com/subgraphs/name/livepeer/livepeer'

    query = """query {
     protocols {
        totalActiveStake
      }
    }"""
    r = requests.post(GRAPH_URL, json={'query': query})
    activeStake = round(int(r.json()["data"]["protocols"][0]["totalActiveStake"])/10**18)
    return activeStake

def get_tally(poll, title, numberVoted):
    GRAPH_URL = 'https://api.thegraph.com/subgraphs/name/livepeer/livepeer'

    query = """query {
     pollTallies(where: {id: "%s"}) {
      yes
      no
     }
    }
    """%(poll)

    r = requests.post(GRAPH_URL, json={'query': query})
    votes = r.json()["data"]["pollTallies"][0]
    votes_y = round(int(votes["yes"])/10**18)
    votes_n = round(int(votes["no"])/10**18)
    votes_t = votes_y + votes_n
    activeStake = get_totalActiveStake()
    message = f"[{title}](https://explorer.livepeer.org/voting/{poll})\n" \
              f"```\n" \
              f"{'Yes:':>4} {str(round(votes_y/votes_t*100,2))+'%':>5} {votes_y:>10,} LPT\n" \
              f"{'No:':>4}  {str(round(votes_n/votes_t*100,2))+'%':>5} {votes_n:>10,} LPT\n\n" \
              f"Participation: {round(votes_t/activeStake*100,2)}%\n" \
              f"{numberVoted} Orchestrators voted\n" \
              f"```"
    return message

# Telegram - send message
def send_telegram(text, chat_id):
    sendURL = TEL_URL + "sendMessage?text={}&chat_id={}&parse_mode=MarkdownV2&disable_web_page_preview=True".format(text, chat_id)
    try:
        requests.get(sendURL)
    except Exception as ex:
        print(ex)

# Discord - send message to predefined channel
def send_discord(text):
    webhook = Webhook.partial(DISCORD_HOOK_ID, DISCORD_HOOK_TOKEN, adapter=RequestsWebhookAdapter())
    try:
        webhook.send(text)
    except Exception as ex:
        print(ex)

# run every ~18 hours
if __name__ == "__main__":
    with open("active_polls.json", "r") as f:
        polls = json.load(f)
    for poll in polls.copy():
        title = polls[poll]["title"]
        numberVoted = len(polls[poll]["voted"])
        message = get_tally(poll, title, numberVoted)
        send_telegram(message, "@LivepeerGovernance")
        send_discord(message)
