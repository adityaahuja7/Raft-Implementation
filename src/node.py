import concurrent.futures as futures
import os
import signal, sys
import numpy as np
import threading
import grpc
import raft_pb2_grpc
import raft_pb2
import time

lock = threading.Lock()


def signal_handler(signal, frame):
    print("➡️  Received interrupt signal...")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

# DEVELOPMENT VARIABLES
ID = int(input("ENTER ID:"))
ALL_PORTS = [4040, 4041, 4042, 4043]
PORT = str(ALL_PORTS[ID])
OTHER_IDS = [i for i in range(len(ALL_PORTS)) if i != ID]
OTHER_PORTS = [port for port in ALL_PORTS if port != PORT]


class raft_serviceServicer(raft_pb2_grpc.raft_serviceServicer):
    def __init__(self, node):
        self.node = node

    def appendEntry(self, request, context):
        self.node.stop_election_timeout()
        self.node.current_role = "Follower"
        response = self.node.follower_recieving_message(request)
        return response

    def requestVote(self, request, context):
        response = self.node.vote_on_new_leader(request)
        return response


class Log:
    def __init__(self, log_file_path):
        self.entries = []
        self.log_file_path = log_file_path
        with open(self.log_file_path, "r") as f:
            for line in f:
                parsed_entry = line.strip().split(" ")
                command, term = " ".join(parsed_entry[:-1]), parsed_entry[-1]
                self.entries.append((command, term))
            f.close()

    def add_entry(self, term, command):
        self.entries.append((command, term))

    def get_last_entry(self):
        # What does this return?
        # assumption second is term?
        return self.entries[-1][0], int(self.entries[-1][1])

    def get_entry(self, index):
        return self.entries[index][0], int(self.entries[index][1])

    def get_entries(self):
        return self.entries

    def print_entries(self):
        for entry in self.entries:
            print(entry)

    def modify_log(self, entries):
        self.entries = entries

    def get_length(self):
        return len(self.entries)

    def dump_log(self):
        with open(self.log_file_path, "w") as f:
            for entry in self.entries:
                f.write(str(entry[0]) + " " + str(entry[1]) + "\n")
            f.close()


class Node:
    def __init__(self):
        self.node_id = None
        self.current_term = None
        self.voted_for = None
        self.log = None
        self.commit_length = None
        self.current_role = None
        self.current_leader = None
        self.votes_recieved = None
        self.sent_length = None
        self.ackedLength = None
        self.election_timer = None
        self.log_file = None
        self.temp = 0
        self.last_term = None

    def initialize_node(self, node_id):
        self.node_id = node_id
        self.current_term = 0
        self.voted_for = None
        self.commit_length = 0
        self.current_role = "Follower"
        self.current_leader = None
        self.votes_recieved = set()
        self.sent_length = {}
        self.acked_length = {}
        self.election_timeout = np.random.uniform(5, 11)
        self.election_timer = threading.Timer(
            self.election_timeout, self.handle_election_timeout
        )
        self.election_timer_alive = False
        if os.path.exists("./log.txt"):
            print("➡️  NODE RESTARTED...")
            self.log_file_path = "./log.txt"
        else:
            print("➡️  NODE INITIALIZED...")
            self.log_file_path = "./log.txt"
            open("./log.txt", "w").close()

        self.log = Log(self.log_file_path)
        self.log.print_entries()

        print("⏰ Election timeout set to:", self.election_timeout)
        server_thread = threading.Thread(target=self.start_server)
        server_thread.daemon = True
        server_thread.start()
        self.start_client()

    def start_client(self):
        while True:
            if self.current_role == "Candidate":
                if self.election_timer and self.election_timer_alive == False:
                    self.send_request_vote()
            elif self.current_role == "Follower":
                if self.election_timer and self.election_timer_alive == False:
                    self.start_election_timeout()
            elif self.current_role == "Leader":
                self.heartbeat()
                time.sleep(1)

    def start_server(self):
        print("PID:", os.getpid())
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        raft_pb2_grpc.add_raft_serviceServicer_to_server(
            raft_serviceServicer(self), server
        )
        port = server.add_insecure_port("[::]:" + PORT)
        error = server.start()
        if error:
            print("❌ Error starting server:", error)
            return
        print("✅ Server started listening on port", port)
        server.wait_for_termination()
        return

    def start_election_timeout(self):
        self.election_timer_alive = True
        self.election_timer = threading.Timer(
            self.election_timeout, self.handle_election_timeout
        )
        self.election_timer.daemon = True
        self.election_timer.start()
        print("⏰ Election timeout started...")

    def stop_election_timeout(self):
        self.election_timer.cancel()
        self.election_timer_alive = False
        print("⏰ Election timeout stopped...")

    def handle_election_timeout(self):
        print("⏰ Election timeout triggered...")
        lock.acquire()
        self.election_timer_alive = False
        self.current_role = "Candidate"
        lock.release()

    def vote_on_new_leader(self, response):
        cTerm = response.term
        CId = response.candidateId
        cLogLength = response.lastLogIndex
        cLogTerm = response.lastLogTerm
        if cTerm > self.current_term:
            self.current_term = cTerm
            self.current_role = "Follower"
            self.voted_for = None
        self.last_term = 0
        if self.log.get_length() > 0:
            _, term = self.log.get_last_entry()
            self.last_term = term
        logOK = (cLogTerm > self.last_term) or (
            (cLogTerm == self.last_term) and (cLogLength >= self.log.get_length())
        )

        response = raft_pb2.RequestVoteResponse()

        if (
            (cTerm == self.current_term)
            and logOK
            and (self.voted_for == CId or self.voted_for == None)
        ):
            print("I VOTED FOR:", CId)
            self.voted_for = CId
            response.voteGranted = True
            response.nodeId = self.node_id
            response.term = self.current_term
        else:
            print("I DID NOT VOTE FOR:", CId)
            response.voteGranted = False
            response.nodeId = self.node_id
            response.term = self.current_term

        return response

    def send_request_vote(self):
        print("🗳  Requesting votes...")
        request_vote_request = raft_pb2.RequestVoteRequest()
        self.voted_for = self.node_id
        self.votes_recieved.add(self.node_id)
        self.current_term = self.current_term + 1
        last_term = 0
        if self.log.get_length() > 0:
            last_term = self.log.get_last_entry()[1]
        request_vote_request.term = self.current_term
        request_vote_request.candidateId = self.node_id
        request_vote_request.lastLogIndex = max(0, self.log.get_length() - 1)
        request_vote_request.lastLogTerm = last_term
        responses = {}
        for ID in OTHER_IDS:
            try:
                channel = grpc.insecure_channel("localhost:" + str(OTHER_PORTS[ID]))
                stub = raft_pb2_grpc.raft_serviceStub(channel)
                response = stub.requestVote(request_vote_request)
                responses[response.nodeId] = response
                print("❎ Response recieved from Node-", response.nodeId)
                self.handle_vote_reponse(response)
            except:
                print("❌ Error sending request to port:", str(OTHER_PORTS[ID]))
        print("VOTES RECIEVED:", len(self.votes_recieved))

        if self.current_role == "Candidate":
            self.start_election_timeout()

    def handle_vote_reponse(self, response):
        responder_id = response.nodeId
        responder_term = response.term
        responder_vote_granted = response.voteGranted
        if (
            self.current_role == "Candidate"
            and responder_term == self.current_term
            and responder_vote_granted
        ):
            self.votes_recieved.add(responder_id)
            if len(self.votes_recieved) > len(ALL_PORTS) / 2:
                self.current_role = "Leader"
                self.current_leader = self.node_id
                self.stop_election_timeout()
                print("🎉 Leader elected:", self.current_leader)
                for ID in OTHER_IDS:
                    try:
                        self.sent_length[ID] = self.log.get_length()
                        self.acked_length[ID] = 0
                        self.replicate_log(self.current_leader, ID)
                    except:
                        print("❌ Error sending request to port:", OTHER_PORTS[ID])
            elif responder_term > self.current_term:
                self.current_term = responder_term
                self.current_role = "Follower"
                self.voted_for = None
                self.stop_election_timeout()

    def replicate_log(self, leaderId, followerId):
        if not self.sent_length[followerId]:
            self.sent_length[followerId] = 0
        prefixLen = self.sent_length[followerId]
        suffix = []
        for i in range(prefixLen, self.log.get_length()):
            suffix.append(self.log.get_entry[i])
        prefixTerm = 0
        if prefixTerm > 0:
            prefixTerm = self.log.get_entry(prefixLen - 1)[1]

        # Send Log request
        suffix_entry = raft_pb2.Entry()

        for entry in suffix:
            suffix_entry.commands.append(str(entry[0]) + " " + str(entry[1]))

        append_entry_request = raft_pb2.AppendEntryRequest()
        append_entry_request.term = self.current_term
        append_entry_request.leaderId = leaderId
        append_entry_request.prevLogIndex = prefixLen
        append_entry_request.prevLogTerm = prefixTerm
        append_entry_request.entries.CopyFrom(suffix_entry)
        append_entry_request.leaderCommit = self.commit_length
        try:
            channel = grpc.insecure_channel("localhost:" + str(OTHER_PORTS[followerId]))
            stub = raft_pb2_grpc.raft_serviceStub(channel)
            response = stub.appendEntry(append_entry_request)
            print("✅ Log replicated to Node-", followerId)
        except:
            print("❌ Error sending request to port:", str(OTHER_PORTS[followerId]))

        return

    def broadcast_message_on_call(self, message):
        if self.current_role == "Leader":
            self.log.add_entry(self.current_term, message.Request)
            self.acked_length[self.node_id] = self.log.get_length()
            for follower_id in OTHER_IDS:
                self.replicate_log(self.node_id, follower_id)
        else:
            # Forward the request to the current Leader
            print("Something to be done here")

    def heartbeat(self):
        if self.current_role == "Leader":
            for follower_id in OTHER_IDS:
                self.replicate_log(self.node_id, follower_id)

    def follower_recieving_message(self, message):
        # Function 6 out of 9
        leader_id = message.leaderId
        term = message.term
        prefixLen = message.prevLogIndex
        prefixTerm = message.prevLogTerm
        leaderCommit = message.leaderCommit
        # problematic
        suffix = message.entries.commands

        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self.stop_election_timeout()

        if term == self.current_term:
            print("👂 Recieved message from Leader-", leader_id)
            self.current_role = "Follower"
            self.current_leader = leader_id

        logOK = (self.log.get_length() >= prefixLen) and (
            prefixLen == 0 or self.log.get_entry(prefixLen)[0] == prefixTerm
        )
        append_entry_response = raft_pb2.AppendEntryResponse()
        append_entry_response.nodeId = self.node_id
        append_entry_response.term = self.current_term
        if term == self.current_term and logOK:
            self.append_entries(prefixLen, leaderCommit, suffix)
            ack = prefixLen + len(suffix)
            append_entry_response.ack = ack
            append_entry_response.success = True
        else:
            append_entry_response.ack = 0
            append_entry_response.success = False

        return append_entry_response

    def append_entries(self, prefixLen, leaderCommit, suffix):
        # Function 7 out of 9
        if len(suffix) > 0 and self.log.get_length() > prefixLen:
            index = min(self.log.get_length(), prefixLen + len(suffix)) - 1
            if self.log.get_entry[index][1] != suffix[index - prefixLen].split()[-1]:
                self.log.modify_log(self.log.get_entries()[0:prefixLen])
        if prefixLen + len(suffix) > self.log.get_length():
            for i in range(self.log.get_length() - prefixLen, len(suffix)):
                command = " ".join(suffix[i].split()[0:-1])
                term = suffix[i].split()[-1]
                self.log.add_entry(term, command)
        if leaderCommit > self.commit_length:
            for i in range(self.commit_length, leaderCommit):
                print("COMMITTED", self.log.get_entry(i)[0])
            self.commit_length = leaderCommit
        return


if __name__ == "__main__":
    node = Node()
    node.initialize_node(ID)
