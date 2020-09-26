import json
import requests
import time
from web3 import Web3
from config_private import TEL_URL, DISCORD_HOOK_ID, DISCORD_HOOK_TOKEN
from config_public import LP_POLL_CREATOR, POLL_CREATION_TOPIC, BONDING_MANAGER_PROXY, BONDING_MANAGER_ABI
from discord import Webhook, RequestsWebhookAdapter

WS_LOCAL = "ws://localhost:8546"
w3 = Web3(Web3.WebsocketProvider(WS_LOCAL))

bonding_manager_proxy = w3.eth.contract(address=BONDING_MANAGER_PROXY, abi=json.loads(BONDING_MANAGER_ABI))

def write_poll_to_json(pollAddress, endBlock, ipfs, title):
    with open("active_polls.json", "r") as f:
        polls = json.load(f)
    polls[pollAddress] = {}
    polls[pollAddress]["endBlock"] = endBlock
    polls[pollAddress]["ipfs"] = ipfs
    polls[pollAddress]["title"] = title
    polls[pollAddress]["voted"] = []
    with open("active_polls.json", "w") as f:
        json.dump(polls, f, indent=1)

def get_poll_title_and_abstract(ipfs):
    r = requests.get(f"https://ipfs.infura.io:5001/api/v0/cat/{ipfs}")
    title = [s[7:] for s in r.json()["text"].split("##")[0].split("\n") if "title" in s][0]
    abstract = max(r.json()["text"].split("##")[1].split("\n"), key=len)
    return title, abstract

def check_pollCreation(fromBlock, toBlock):
    """Checks for new poll creation between fromBlock and toBlock.
    If an event exists, get the contract address of the poll and create the link to the livepeer website
    """
    pollCreation_filter = w3.eth.filter({
    "fromBlock": fromBlock,
    "toBlock": toBlock,
    "address": LP_POLL_CREATOR,
    "topics": [POLL_CREATION_TOPIC],
    })
    for event in pollCreation_filter.get_all_entries():
        blockNumber = event["blockNumber"]
        pollAddress = "0x" + event["topics"][1].hex()[26:]
        endBlock = w3.toInt(hexstr=event["data"][2:][64:128])
        tx = event["transactionHash"].hex()
        ipfs = w3.toText(hexstr=event["data"][2:][320:]).rstrip("\x00")
        title, abstract = get_poll_title_and_abstract(ipfs)
        write_poll_to_json(pollAddress, endBlock, ipfs, title)           
        message = f"New poll created at block {blockNumber}: {title}!\n\n" \
                f"Abstract: {abstract}\n\n" \
                f"Please check [the Livepeer Explorer](https://explorer.livepeer.org/voting/{pollAddress}) for more information and to vote!\n\n" \
                f"[Transaction link](https://etherscan.io/tx/{tx})"
        send_telegram(message, "@LivepeerGovernance")
        send_discord(message)

def get_orchestrator_votes(fromBlock, toBlock, polls, pollAddress, pollTitle):
    """Checks for votes of existing polls between fromBlock and toBlock.
    If an event exists, check if the caller is an orchestrator. Append to the json and notify.
    """
    voting_filter = w3.eth.filter({
    "fromBlock": fromBlock,
    "toBlock": toBlock,
    "address": pollAddress,
    "topics": ['0xf668ead05c744b9178e571d2edb452e72baf6529c8d72160e64e59b50d865bd0'],
    })
    for event in voting_filter.get_all_entries():
        caller = w3.toChecksumAddress("0x" + event["topics"][1].hex()[26:])
        if bonding_manager_proxy.functions.isRegisteredTranscoder(caller).call():
            # add orchestrator to "voted" in json
            polls[pollAddress.lower()]["voted"].append(caller)            
            votes = bonding_manager_proxy.functions.transcoderTotalStake(caller).call()/10**18
            if event["data"][-1] == "0":
                choice = "Yes"
            elif event["data"][-1] == "1":
                choice = "No"
            tx = event["transactionHash"].hex()
            message = f"Orchestrator [{caller[:8]}](https://explorer.livepeer.org/accounts/{caller}/campaign) voted!\n\n" \
                    f"Proposal: {pollTitle}\n" \
                    f"Vote: {choice} - for {round(votes):,} LPT\n\n" \
                    f"Please check [the Livepeer Explorer](https://explorer.livepeer.org/voting/{pollAddress}) for more information!\n" \
                    f"If you do not agree with your orchestrator's choice, you can overrule it by voting yourself.\n\n" \
                    f"[Transaction link](https://etherscan.io/tx/{tx})"
            send_telegram(message, "@LivepeerGovernance")
            send_discord(message)
            time.sleep(1)

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

def get_final_tally(poll, pollTitle):
    """Gets the tally of a poll from the subgraph.
    """
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
    message = f"The following poll has ended: [{pollTitle}](https://explorer.livepeer.org/voting/{poll})\n" \
              f"Result:\n" \
              f"```\n" \
              f"{'Yes:':>4} {str(round(votes_y/votes_t*100,2))+'%':>5} {votes_y:>10,} LPT\n" \
              f"{'No:':>4}  {str(round(votes_n/votes_t*100,2))+'%':>5} {votes_n:>10,} LPT\n\n" \
              f"Participation: {round(votes_t/activeStake*100,2)}%\n" \
              f"```"
    send_telegram(message, "@LivepeerGovernance")
    send_discord(message)

# Telegram - send message
def send_telegram(text, chat_id):
    sendURL = TEL_URL + "sendMessage?text={}&chat_id={}&parse_mode=Markdown&disable_web_page_preview=True".format(text, chat_id)
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

def main():
    # Read previous blocknumber and get new blocknumber (-5)
    # If there is no entry in the txt file, get current blocknumber - 50 (~10min ago)
    with open('block_record.txt', 'r') as fh:
        blockOld = fh.readlines()
    if not blockOld:
        blockOld = w3.eth.blockNumber - 50
    else:
        blockOld = int(blockOld[0])
    block = w3.eth.blockNumber - 5
    # Check for new polls
    try:
        check_pollCreation(blockOld, block)
        # Get orchestrator votes
        with open("active_polls.json", "r") as f:
            polls = json.load(f)
        for poll in polls.copy():
            title = polls[poll]["title"]
            get_orchestrator_votes(blockOld, block, polls, w3.toChecksumAddress(poll), title)
            # If a poll has ended, get final tally & remove from json
            if block >= polls[poll]["endBlock"]:
                get_final_tally(poll, title)
                del polls[poll]
        with open("active_polls.json", "w") as f:
            json.dump(polls, f, indent=1)
        # Write new processed blocknumber to file
        with open('block_record.txt', 'w') as fh:
            fh.write(str(block))
    except Exception as ex:
        print(ex)

# run every ~100 blocks / 20 minutes
if __name__ == '__main__':
    main()