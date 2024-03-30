import concurrent.futures as futures
import os
import signal, sys
import numpy as np
import threading
import grpc
import raft_pb2_grpc
import raft_pb2
import time
import custom_timer

# |--------------------------------------|
# | DEVELOPMENT VARIABLES                |
# |--------------------------------------|

lock = threading.Lock()
lease_lock = threading.Lock()


def signal_handler(signal, frame):
    print("➡️  Received interrupt signal...")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

ID = int(input("ENTER ID:"))
ALL_PORTS = [4040, 4041, 4042, 4043]
PORT = str(ALL_PORTS[ID])
OTHER_IDS = [i for i in range(len(ALL_PORTS)) if i != ID]

# |--------------------------------------|
# | gRPC SERVICER CLASS                  |
# |--------------------------------------|


class raft_serviceServicer(raft_pb2_grpc.raft_serviceServicer):
    def __init__(self, node):
        self.node = node

    def appendEntry(self, request, copntext):
        if self.node.current_role != "Leader":
            self.node.stop_election_timeout()
        response = self.node.follower_recieving_message(request)
        return response

    def requestVote(self, request, context):
        response = self.node.vote_on_new_leader(request)
        return response

    def serveClient(self, request, context):
        print("Request Recieved:", request.Request)
        return self.node.handle_broadcast_message(request)


# |--------------------------------------|
# | LOG CLASS                            |
# |--------------------------------------|


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
        self.dump_log()

    def get_last_entry(self):
        return self.entries[-1][0], int(self.entries[-1][1])

    def get_entry(self, index):
        return self.entries[index][0], int(self.entries[index][1])

    def get_entries(self):
        return self.entries

    def get_entry_by_key(self, key):
        value = None
        for entry in self.entries:
            if entry[0].split()[0] == "SET" and entry[0].split()[1] == key:
                value = entry[0].split()[2]
        return value

    def print_entries(self):
        for entry in self.entries:
            print(entry)

    def modify_log(self, entries):
        self.entries = entries
        self.dump_log()

    def get_length(self):
        return len(self.entries)

    def dump_log(self):
        open(self.log_file_path, "w").close()
        with open(self.log_file_path, "w") as f:
            for entry in self.entries:
                f.write(str(entry[0]) + " " + str(entry[1]) + "\n")
            f.close()


# |--------------------------------------|
# | NODE CLASS                           |
# |--------------------------------------|


class Node:

    # |--------------------------------------|
    # | NODE INITIALIZATION                  |
    # |--------------------------------------|

    def __init__(self):
        self.node_id = None
        self.current_term = None
        self.max_lease_duration = None  # system
        self.lease_duration = None  # mine
        self.lease_timer_alive = None  # mine
        self.lease_timer = None
        self.can_write = None
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
        self.max_lease_duration = 3  # system
        self.lease_duration = 0  # mine
        self.lease_timer_alive = False  # mine
        self.lease_timer = None
        self.can_write = False
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
        if os.path.exists("./logs/" + "log_" + str(self.node_id) + ".txt"):
            print("➡️  NODE RESTARTED...")
            self.log_file_path = "./logs/" + "log_" + str(self.node_id) + ".txt"
            self.log = Log(self.log_file_path)
            self.current_term = self.log.get_last_entry()[1]
        else:
            print("➡️  NODE INITIALIZED...")
            if not os.path.exists("./logs/"):
                os.mkdir("./logs/")
            open("./logs/" + "log_" + str(self.node_id) + ".txt", "w").close()
            self.log_file_path = "./logs/" + "log_" + str(self.node_id) + ".txt"
            self.log = Log(self.log_file_path)

        print("📒  Current Log:", self.log.get_entries())

        print("⏰ Election timeout set to:", self.election_timeout)
        server_thread = threading.Thread(target=self.start_server)
        server_thread.daemon = True
        server_thread.start()
        self.start_client()

    # |--------------------------------------|
    # | INITIALIZE CLIENT AND SERVER THREADS |
    # |--------------------------------------|

    def start_client(self):
        while True:
            if self.current_role == "Candidate":
                if self.election_timer and self.election_timer_alive == False:
                    self.send_request_vote()
            elif self.current_role == "Follower":
                if (
                    self.election_timer
                    and self.election_timer_alive == False
                    and self.lease_timer_alive == False
                ):
                    self.start_election_timeout()
            elif self.current_role == "Leader":
                self.heartbeat()  # CHANGE THIS TO ACCOMODATE LEADER LEASE
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

    # |--------------------------------------|
    # | HANDLE ELECTION PROCESS              |
    # |--------------------------------------|

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

    def start_lease(self):
        self.lease_timer_alive = True
        self.log.add_entry("NO-OP", self.current_term)
        self.lease_timer = custom_timer.LeaseTimer(
            self.max_lease_duration, self.handle_lease_timeout
        )
        self.lease_timer.start()
        print("⏰ Lease started...")

    def renew_lease(self, renew_time):
        if self.lease_timer_alive:
            self.stop_lease()
        self.lease_timer_alive = True
        self.lease_timer = custom_timer.LeaseTimer(
            renew_time, self.handle_lease_timeout
        )
        self.lease_timer.start()
        print("⏰ Lease started...")

    def toggle_can_write(self):
        self.can_write = True

    def stop_lease(self):
        self.lease_timer.cancel()
        self.lease_timer_alive = False
        print("⏰ Lease stopped...")

    def handle_lease_timeout(self):
        print("⏰ Lease timeout triggered...")
        lease_lock.acquire()
        self.current_role = "Follower"
        self.current_leader = None
        self.lease_duration = 0
        self.lease_timer_alive = False
        self.can_write = False
        lease_lock.release()

    def vote_on_new_leader(self, request):
        cTerm = request.term
        CId = request.candidateId
        cLogLength = request.lastLogIndex
        cLogTerm = request.lastLogTerm
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
            print("❎  I VOTED FOR:", CId)
            self.voted_for = CId
            response.voteGranted = True
            response.nodeId = self.node_id
            response.term = self.current_term
        else:
            print("❎ I DID NOT VOTE FOR:", CId)
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
        request_vote_request.lastLogIndex = max(0, self.log.get_length())
        request_vote_request.lastLogTerm = last_term
        responses = {}
        self.lease_duration = 0
        for ID in OTHER_IDS:
            # try:
            channel = grpc.insecure_channel("localhost:" + str(ALL_PORTS[ID]))
            stub = raft_pb2_grpc.raft_serviceStub(channel)
            response = stub.requestVote(request_vote_request)
            responses[response.nodeId] = response
            if (
                self.lease_timer
                and response.leaseDuration > self.lease_timer.time_left()
            ):
                self.lease_duration = response.leaseDuration
                self.renew_lease(self.lease_duration)
                threading.Timer(self.lease_duration, self.toggle_can_write).start()

            print("❎ Response recieved from Node-", response.nodeId)
            self.handle_vote_reponse(response)
        # except:
        #     print("❌ Error sending request to port:", str(ALL_PORTS[ID]))

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
                        print("❌ Error sending request to port:", ALL_PORTS[ID])
            elif responder_term > self.current_term:
                self.current_term = responder_term
                self.current_role = "Follower"
                self.voted_for = None
                self.stop_election_timeout()
        else:
            pass

    # |--------------------------------------|
    # | LEADER FUNCTIONALITY                 |
    # |--------------------------------------|

    def replicate_log(self, leaderId, followerId):
        if followerId not in self.sent_length.keys():
            self.sent_length[followerId] = 0
        prefixLen = self.sent_length[followerId]
        suffix = [
            self.log.get_entry(i) for i in range(prefixLen, self.log.get_length())
        ]

        prefixTerm = 0
        if prefixLen > 0:
            prefixTerm = self.log.get_entry(prefixLen - 1)[1]

        suffix_entry = raft_pb2.Entry()
        for entry in suffix:
            suffix_entry.commands.append(f"{entry[0]} {entry[1]}")

        append_entry_request = raft_pb2.AppendEntryRequest(
            term=self.current_term,
            leaderId=leaderId,
            prevLogIndex=prefixLen,
            prevLogTerm=prefixTerm,
            entries=suffix_entry,
            leaderCommit=self.commit_length,
            leaseDuration=self.max_lease_duration,
        )

        try:
            channel = grpc.insecure_channel(f"localhost:{ALL_PORTS[followerId]}")
            stub = raft_pb2_grpc.raft_serviceStub(channel)
            response = stub.appendEntry(append_entry_request)
            print(f"✅ Log replicated to Node-{followerId}")
        except:
            print("❌ Error sending request to port:", str(ALL_PORTS[followerId]))
            return

        self.recieve_log_ack(
            response.nodeId, response.term, response.ack, response.success
        )

        return response

    def recieve_log_ack(self, follower, term, ack, success):
        # Function 8 out of 9
        if term == self.current_term and self.current_role == "Leader":
            if success == True and ack >= self.acked_length[follower]:
                self.sent_length[follower] = ack
                self.acked_length[follower] = ack
                self.commit_log_entries()
            elif self.sent_length[follower] > 0:
                self.sent_length[follower] -= 1
                self.replicate_log(self.node_id, follower)
        elif term > self.current_term:
            self.current_term = term
            self.current_role = "Follower"
            self.voted_for = None
            self.stop_election_timeout()

    def set_of_acks(self, length):
        # Helper Function 9 out of 9
        count = 0
        for i in self.acked_length.keys():
            if self.acked_length[i] >= length:
                count += 1
        return count

    def commit_log_entries(self):
        # Function 9 out of 9
        minacks = len(ALL_PORTS) / 2
        ready = []
        for i in range(1, self.log.get_length() + 1):
            if self.set_of_acks(i) >= minacks:
                ready.append(i)
        if (
            len(ready) > 0
            and max(ready) > self.commit_length
            and self.log.get_entry(max(ready) - 1)[1] == self.current_term
        ):
            for i in range(self.commit_length, max(ready)):
                print("STATE COMMITED:", self.log.get_entry(i)[0])
            self.commit_length = max(ready)
        return

    def handle_broadcast_message(self, message):
        user_response = raft_pb2.ServeClientReply()
        user_response.LeaderID = str(self.current_leader)
        if self.current_role == "Leader":
            if message.Request.split()[0] == "GET":
                if not self.can_write:
                    user_response.Success = False
                    user_response.Data = "Leader does not have lease!."
                else:
                    user_response.Success = True
                    user_response.Data = self.log.get_entry_by_key(
                        message.Request.split()[1]
                    )

            elif message.Request.split()[0] == "SET":
                if not self.can_write:
                    user_response.Success = False
                    user_response.Data = "Leader does not have lease!."
                else:
                    count_success = 0
                    for follower_id in OTHER_IDS:
                        response = self.replicate_log(self.node_id, follower_id)
                        if response.success:
                            count_success += 1
                    if count_success >= len(ALL_PORTS) / 2:
                        user_response.Success = True
                        user_response.Data = (
                            str(message.Request) + " successfully committed."
                        )
            return user_response
        
        else:
            print("📝  Recieved client request...")
            print("⏩ Redirecting to Leader-", self.current_leader)
            # try:
            channel = grpc.insecure_channel(
                "localhost:" + str(ALL_PORTS[self.current_leader])
            )
            stub = raft_pb2_grpc.raft_serviceStub(channel)
            response = stub.serveClient(message)
            print("📝  Response from Leader-", self.current_leader, ":", response)
            return response
            # except:
            #     print("❌ Error forwarding request to leader port:", str(ALL_PORTS[self.current_leader]))

    def heartbeat(self):
        if self.current_role == "Leader":
            responses = []
            for follower_id in OTHER_IDS:
                _ = self.replicate_log(self.node_id, follower_id)
                if _:
                    responses.append(_)

            count_success = 0
            for response in responses:
                if response.success:
                    count_success += 1
            print("♥ Successful Heartbeat Count:", count_success)

            if count_success >= len(ALL_PORTS) / 2:
                self.renew_lease(self.max_lease_duration)

    # |--------------------------------------|
    # | FOLLOWER FUNCTIONALITY               |
    # |--------------------------------------|

    def follower_recieving_message(self, message):
        # Function 6 out of 9
        leader_id = message.leaderId
        term = message.term
        prefixLen = message.prevLogIndex
        prefixTerm = message.prevLogTerm
        leaderCommit = message.leaderCommit
        suffix = message.entries.commands
        self.lease_duration = message.leaseDuration

        self.renew_lease(self.lease_duration)
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self.stop_election_timeout()

        if term == self.current_term:
            print("👂 Recieved message from Leader-", leader_id)
            self.current_role = "Follower"
            self.current_leader = leader_id

        logOK = (self.log.get_length() >= prefixLen) and (
            prefixLen == 0 or self.log.get_entry(prefixLen - 1)[1] == prefixTerm
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
            if self.log.get_entry(index)[1] != suffix[index - prefixLen].split()[-1]:
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
