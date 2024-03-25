import os
import sys
import numpy as np
import threading
import grpc
import raft_pb2
import time


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
            
        
    def initialize_node(self,node_id):
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
        self.election_timeout = np.random.uniform(5,11)
        self.election_timer = threading.Timer(self.election_timeout, self.handle_election_timeout)
        if os.path.exists("./log.txt"):
            print("➡️  NODE RESTARTED...")
            self.log_file = open("./log.txt")
        else:
            print("➡️  NODE INITIALIZED...")
            self.log_file = open("./log.txt",'w')
        print("⏰ Electiom timeout set to:", self.election_timeout)
        
        
    def start_election_timeout(self):
        self.election_timer.start()
        print("⏰ Election timeout started...")
    
    def stop_election_timeout(self):
        self.election_timer.cancel()
        print("⏰ Election timeout stopped...")
        
    
    def handle_election_timeout(self):
        # TODO:Handle the election logic
        return
        
        

if __name__ == "__main__":
    server = Node(1)
    server.initialize_node()
    time.sleep(200)
    
    
        
