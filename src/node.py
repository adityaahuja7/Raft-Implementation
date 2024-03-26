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
PORT = input("ENTRY PORT: ")
ALL_PORTS = [str(4040), str(4041)]
OTHER_PORTS = [port for port in ALL_PORTS if port != PORT]


class raft_serviceServicer(raft_pb2_grpc.raft_serviceServicer):
    def __init__(self, node):
        self.node = node

    def appendEntry(self, request, context):
        print(request)
        response = raft_pb2.AppendEntryResponse()
        response.term = 10291
        response.success = True
        return response

    def requestVote(self, request, context):
        print("Request received:", request)
        response = raft_pb2.RequestVoteResponse()
        response.term = 10291  
        response.voteGranted = True
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
        return self.entries[-1][0], int(self.entries[-1][1])

    def get_entry(self, index):
        return self.entries[index]

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
                self.send_request_vote()
                self.current_role = "Follower"
            elif self.current_role == "Follower":
                if self.election_timer and self.election_timer_alive == False:
                    self.start_election_timeout()
            elif self.current_role == "Leader":
                self.send_replicate_log()
        print("NO BUGS!")

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
        self.election_timer = threading.Timer(self.election_timeout, self.handle_election_timeout)
        self.election_timer.daemon = True
        self.election_timer.start()
        print("⏰ Election timeout started...")

    def stop_election_timeout(self):
        self.election_timer.cancel()
        print("⏰ Election timeout stopped...")

    def handle_election_timeout(self):
        print("⏰ Election timeout triggered...")
        lock.acquire()
        self.election_timer_alive = False
        self.current_role = "Candidate"
        lock.release()

    def send_request_vote(self):
        print("🗳 Requesting votes...")
        request_vote_request = raft_pb2.RequestVoteRequest()
        self.voted_for = self.node_id
        self.votes_recieved.add(self.node_id)
        request_vote_request.term = self.current_term + 1
        last_term = 0
        if self.log.get_length()> 0:
            last_term = self.log.get_last_entry()[1]
        
        request_vote_request.term = self.current_term
        request_vote_request.candidateId = self.node_id
        request_vote_request.lastLogIndex = max(0, self.log.get_length() - 1)
        request_vote_request.lastLogTerm = last_term
        
        for port in OTHER_PORTS:
            try:
                channel = grpc.insecure_channel("localhost:" + str(port))
                stub = raft_pb2_grpc.raft_serviceStub(channel)
                response = stub.requestVote(request_vote_request)
                print(response)
            except:
                print("❌ Error sending request vote to port:", port)
                
        # manage responses
        


if __name__ == "__main__":

    node = Node()
    node.initialize_node(int(PORT))
