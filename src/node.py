import concurrent.futures as futures
import os
import signal, sys
import numpy as np
import threading
import grpc
import raft_pb2_grpc
import raft_pb2
import time

def signal_handler(signal, frame):
    print("➡️  Received interrupt signal...")
    sys.exit(0)
    
signal.signal(signal.SIGINT, signal_handler)
    
# DEVELOPMENT VARIABLES
PORT = input("ENTRY PORT: ")


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
        print("Request Vote RPC Called...")


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
        self.log_file = None

    def initialize_node(self, node_id):
        self.node_id = node_id
        self.current_term = 0
        self.voted_for = None
        self.log = []
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
        if os.path.exists("./log.txt"):
            print("➡️  NODE RESTARTED...")
            self.log_file = open("./log.txt")
        else:
            print("➡️  NODE INITIALIZED...")
            self.log_file = open("./log.txt", "w")

        print("⏰ Election timeout set to:", self.election_timeout)
        server_thread = threading.Thread(target=self.start_server)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(3600)

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
        self.election_timer.start()
        print("⏰ Election timeout started...")

    def stop_election_timeout(self):
        self.election_timer.cancel()
        print("⏰ Election timeout stopped...")

    def handle_election_timeout(self):
        self.current_term = self.current_term + 1
        self.current_role = "Candidate"
        self.voted_for = self.node_id
        self.votes_recieved.add(self.node_id)
        last_term = 0
        if len(self.log) > 0:
            last_term = self.log[-1].term

        return


if __name__ == "__main__":
    
    node = Node()
    node.initialize_node(1)
