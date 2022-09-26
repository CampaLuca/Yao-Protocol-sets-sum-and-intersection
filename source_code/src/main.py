#!/usr/bin/env python3
import ot
import util
import yao
from abc import ABC, abstractmethod
import circuit_generator
import os
import atexit


class YaoGarbler(ABC):
    """An abstract class for Yao garblers (e.g. Alice)."""
    def __init__(self, circuits):
        circuits = util.parse_json(circuits)
        self.name = circuits["name"]
        self.circuits = []

        for circuit in circuits["circuits"]:
            garbled_circuit = yao.GarbledCircuit(circuit)
            pbits = garbled_circuit.get_pbits()
            entry = {
                "circuit": circuit,
                "garbled_circuit": garbled_circuit,
                "garbled_tables": garbled_circuit.get_garbled_tables(),
                "keys": garbled_circuit.get_keys(),
                "pbits": pbits,
                "pbits_out": {w: pbits[w]
                              for w in circuit["out"]},
            }
            self.circuits.append(entry)

    @abstractmethod
    def start(self):
        pass


class Alice(YaoGarbler):
    """Alice is the creator of the Yao circuit.

    Alice creates a Yao circuit and sends it to the evaluator along with her
    encrypted inputs. Alice will finally print the truth table of the circuit
    for her inputs and the outputs.

    Alice does not know Bob's inputs. Bob's inputs will be printed by Bob.

    Attributes:
        circuits: the JSON file containing circuits
        set: the set of values of Alice (only integers)
        oblivious_transfer: Optional; enable the Oblivious Transfer protocol
            (True by default).
        print_mode: Optional; Possible values:
                                    circuit: prints the truth table
                                    table: prints the tables sent by Alice to Bob
                    Default: circuit
        operation: Optional; Possible values:
                                0: set sum
                                1: common values between two sets
                    Default: 0
    """
    def __init__(self, circuits, set, oblivious_transfer=True, print_mode="circuit", operation=0):
        self.__operation = operation
        self._print_mode = print_mode
        self.modes = {
            "circuit": self.print,
            "table": self._print_tables,
        }
        self.set = set
        self.max_bit_length = 0
        self.socket = util.GarblerSocket()
        self.ot = ot.ObliviousTransfer(self.socket, enabled=oblivious_transfer)
        self.__exchange_max_bit_length()
        if self.__share_chosen_operation():
            circuit_path = self.__create_circuit(circuits['filename'], circuits['id_name'], circuits['circuit_name'])
            super().__init__(circuit_path)

        self.expected_output = ExpectedOutput(operation)
        self.expected_output.print_expected_output()

    def __exchange_max_bit_length(self):
        max_bit_length = self.socket.send_wait({"question": 1, "length": len(bin(sum(self.set))[2:])})
        # 1 means give me max dim set
        self.max_bit_length = max_bit_length + 1

    def __share_chosen_operation(self):
        return self.socket.send_wait({"operation":self.__operation})

    def __create_circuit(self, circuit_filename, id_name, circuit_name):
        # Alice is the circuit creator
        return circuit_generator.create_circuit(circuit_filename, self.max_bit_length, circuit_name,
                                         id_name, operation=self.__operation, alice_set_cardinality=len(self.set))

    def __interpret_result(self, str_results):
        if self.__operation == 0:  # sum
            for str_result in str_results:
                result = str_result.replace(' ', "")
                result = int(result[::-1], 2)
                print(f'The sum of the elements is: {result}')
            self.expected_output.compare_outputs(result)

        if self.__operation == 1:  # compare
            common_values = set()
            for str_result in str_results:
                result = str_result.replace(' ', "")
                equality_bit = result[0]
                if equality_bit == "1":
                    common_values.add(int(result[1:][::-1], 2))

            print("Common values: ", end=" ")
            for val in common_values:
                print(val, end=" ")

            self.expected_output.compare_outputs(common_values)

    def start(self):
        """Start Yao protocol."""
        for circuit in self.circuits:
            to_send = {
                "circuit": circuit["circuit"],
                "garbled_tables": circuit["garbled_tables"],
                "pbits_out": circuit["pbits_out"],
            }
            if self._print_mode == "circuit":
                self.socket.send_wait(to_send)
            self.modes[self._print_mode](circuit)

    def _print_tables(self, entry):
        """Print garbled tables."""
        entry["garbled_circuit"].print_garbled_tables()

    def print(self, entry):
        """Print circuit evaluation for all Bob and Alice inputs.

        Args:
            entry: A dict representing the circuit to evaluate.
        """
        circuit, pbits, keys = entry["circuit"], entry["pbits"], entry["keys"]
        outputs = circuit["out"]
        a_wires = circuit.get("alice", [])  # Alice's wires
        a_inputs = {}  # map from Alice's wires to (key, encr_bit) inputs
        b_wires = circuit.get("bob", [])  # Bob's wires
        b_keys = {  # map from Bob's wires to a pair (key, encr_bit)
            w: self._get_encr_bits(pbits[w], key0, key1)
            for w, (key0, key1) in keys.items() if w in b_wires
        }
        N = len(a_wires) + len(b_wires)

        print(f"======== {circuit['id']} ========")

        """print(f"  Alice{a_wires} = {str_bits_a} "
                  f"Bob{b_wires} = {str_bits_b}  "
                  f"Outputs{outputs} = {str_result}")
                  
                  FOR DEBUGGING """
        str_results = []

        if self.__operation == 0:
            bits_a = [int(i) for i in bin(sum(self.set))[2:][::-1]]  # Alice's inputs
            if len(bits_a) < self.max_bit_length:
                for i in range(self.max_bit_length - len(bits_a)):
                    bits_a.append(0)
            # Map Alice's wires to (key, encr_bit)
            for i in range(len(a_wires)):
                a_inputs[a_wires[i]] = (keys[a_wires[i]][bits_a[i]],
                                        pbits[a_wires[i]] ^ bits_a[i])

            # Send Alice's encrypted inputs and keys to Bob
            result = self.ot.get_result(a_inputs, b_keys)
            str_bits_a = [str(i) for i in bits_a]
            str_bits_a = ' '.join(str_bits_a[:len(a_wires)])
            str_result = ' '.join([str(result[w]) for w in outputs])
            str_results.append(str_result)
            print(f"Alice{a_wires} = {str_bits_a}\t\t"
                  f"Outputs{outputs} = {str_result}")

        if self.__operation == 1:
            bits_a = []
            for value in self.set:
                bits_value = [int(i) for i in bin(value)[2:][::-1]]
                if len(bits_value) < self.max_bit_length:
                    for i in range(self.max_bit_length - len(bits_value)):
                        bits_value.append(0)
                bits_a = bits_a + bits_value

            # Map Alice's wires to (key, encr_bit)
            for i in range(len(a_wires)):
                a_inputs[a_wires[i]] = (keys[a_wires[i]][bits_a[i]],
                                        pbits[a_wires[i]] ^ bits_a[i])

            # Send Alice's encrypted inputs and keys to Bob
            result = self.ot.get_result(a_inputs, b_keys)

            str_bits_a = [str(i) for i in bits_a]
            str_bits_a = ' '.join(str_bits_a[:len(a_wires)])
            print(f"Alice{a_wires} = {str_bits_a}\t\t")
            while result.get("end") is None:
                str_result = ' '.join([str(result[w]) for w in outputs])
                str_results.append(str_result)
                print(f"Outputs{outputs} = {str_result}")
                result = self.ot.get_result(a_inputs, b_keys)

        # Format output
        self.__interpret_result(str_results)
        print()

    @staticmethod
    def _get_encr_bits(pbit, key0, key1):
        return (key0, 0 ^ pbit), (key1, 1 ^ pbit)


class Bob:
    """Bob is the receiver and evaluator of the Yao circuit.

    Bob receives the Yao circuit from Alice, computes the results and sends
    them back. It prints his inputs every time.

    Args:
        set: the set of values of Alice (only integers)
        oblivious_transfer: Optional; enable the Oblivious Transfer protocol
            (True by default).
    """
    __operation = None

    def __init__(self, set, oblivious_transfer=True):
        self.socket = util.EvaluatorSocket()
        self.ot = ot.ObliviousTransfer(self.socket, enabled=oblivious_transfer)
        self.set = set
        self.max_bit_length = 0

    def update_set(self, new_set):
        self.set = new_set

    def listen(self):
        """Start listening for Alice messages."""

        try:
            for entry in self.socket.poll_socket():
                #entry = self.socket.receive()

                if not entry.get("operation") is None:
                    self.__operation = entry["operation"]
                    self.socket.send(True)
                elif not entry.get("question") is None and entry["question"] == 1:
                    print("\nAlice asks for max bit length ...")
                    length = len(bin(sum(self.set))[2:])
                    if length > entry["length"]:
                        self.max_bit_length = length + 1
                        self.socket.send(length)
                    else:
                        self.max_bit_length = entry["length"] + 1
                        self.socket.send(entry["length"])
                else:
                    self.socket.send(True)
                    self.send_evaluation(entry)
        except KeyboardInterrupt:
            print("Closing connection")


    def send_evaluation(self, entry):
        """Evaluate yao circuit for all Bob and Alice's inputs and
        send back the results.

        Args:
            entry: A dict representing the circuit to evaluate.
        """
        circuit, pbits_out = entry["circuit"], entry["pbits_out"]
        garbled_tables = entry["garbled_tables"]
        a_wires = circuit.get("alice", [])  # list of Alice's wires
        b_wires = circuit.get("bob", [])  # list of Bob's wires
        N = len(a_wires) + len(b_wires)

        print(f"Received {circuit['id']}")

        if self.__operation == 0:
            bits_b = [int(i) for i in bin(sum(self.set))[2:][::-1]]  # Bob's inputs
            if len(bits_b) < self.max_bit_length:
                for i in range(self.max_bit_length - len(bits_b)):
                    bits_b.append(0)

            # Create dict mapping each wire of Bob to Bob's input
            b_inputs_clear = {
                b_wires[i]: bits_b[i]
                for i in range(len(b_wires))
            }

            str_bits_b = [str(i) for i in bits_b]
            str_bits_b = ' '.join(str_bits_b[:len(b_wires)])
            print(f"Bob{b_wires} = {str_bits_b}\t\t")
            # Evaluate and send result to Alice
            self.ot.send_result(circuit, garbled_tables, pbits_out,
                                b_inputs_clear)

        if self.__operation == 1:

            # create permutation
            bob_permutated_inputs = util.get_single_permutation(self.set)

            for value in bob_permutated_inputs:
                bits_b = [int(i) for i in bin(value)[2:][::-1]]  # Bob's inputs
                if len(bits_b) < self.max_bit_length:
                    for i in range(self.max_bit_length - len(bits_b)):
                        bits_b.append(0)

                # Create dict mapping each wire of Bob to Bob's input
                b_inputs_clear = {
                    b_wires[i]: bits_b[i]
                    for i in range(len(b_wires))
                }

                str_bits_b = [str(i) for i in bits_b]
                str_bits_b = ' '.join(str_bits_b[:len(b_wires)])
                print(f"Bob{b_wires} = {str_bits_b}\t\t")
                # Evaluate and send result to Alice
                self.ot.send_result(circuit, garbled_tables, pbits_out,
                                    b_inputs_clear)

            self.ot.send_result(circuit, garbled_tables, pbits_out,
                                b_inputs_clear, end=True)


class ExpectedOutput:
    """
    Only for debugging / educational purposes
    The class will be used by Alice and provides a way to check if the result from yao's computation is equal
    to the result form the normal way of computing it.
    """
    alice_set = None
    bob_set = None
    expected_output = None

    def __init__(self, operation):
        self.__operation = operation
        file_path = "./sets/alice_set.txt" if os.path.dirname(__file__) is None or os.path.dirname(__file__) == "" else os.path.dirname(__file__) + "/sets/alice_set.txt"
        file_path = file_path.replace(".txt", "")
        file_path = file_path + '.txt'

        with open(file_path, 'r') as setfile:
            self.alice_set = [int(x) for x in next(setfile).split()]
            setfile.close()

        file_path = file_path.replace("alice", "bob")
        with open(file_path, 'r') as setfile:
            self.bob_set = [int(x) for x in next(setfile).split()]
            setfile.close()

    def print_expected_output(self):
        if self.__operation == 0:  # sum
            self.expected_output = sum(self.alice_set)+sum(self.bob_set)
            print(f"The sum of the elements from Bob and Alice should be: {self.expected_output}")

        if self.__operation == 1:  # cmp
            alice = set(self.alice_set)
            bob = set(self.bob_set)
            self.expected_output = alice.intersection(bob)
            print(f"The common elements between the Bob and Alice's sets are: {self.expected_output}")

    def compare_outputs(self, out):
        if out == self.expected_output:
            print("[CORRECT] The yao's output is equal to the one computed in normal way.")
            return True
        else:
            print("[ERROR] The output is not equal to the one computed in normal way")
            return False


"""
The function saves the chosen set to a file placed in src/sets/ from the garbled-circuit directory
:param actor: bob or alice
:param actor_set: the related set of integers
"""
def save_set_to_file(actor, actor_set):
    name = "alice_set" if actor == "alice" else "bob_set"
    file_path = "./sets/"+name if os.path.dirname(__file__) is None or os.path.dirname(__file__) == "" else os.path.dirname(__file__) + "/sets/"+name
    file_path = file_path.replace(".txt", "")
    file_path = file_path + '.txt'
    with open(file_path, mode='w+') as setfile:
        set_values = ' '.join([str(w) for w in actor_set])
        setfile.write(set_values)
        setfile.close()

    return file_path


# necessary in order to deal with the shell simulation in order to
# change bob's set values without restart the entire process
bob_instance = None
bob_set_path = None


"""
This function intercepts the sequence Ctrl-C.
It prevents the exit from the program by providing a simulated shell with 4 possible commands:
    help: prints the possible commands 
    exit: exits from the program
    new set: gives the possibility to change the set previously assigned to bob
    continue: it returns to listen Alice's messages
"""
def go_to_dev_mode():
    if bob_instance is not None:
        while True:
            value = input("type 'help' for major information > ")
            if value == "help":
                print("Commands:\n\tcontinue (it restores the last session)\n\tnew set (Gives you the possibility to "
                      "type a new bob's set\n\texit (Exit from the program)\n")
            elif value == "continue":
                bob_instance.listen()

            elif value == "new set":
                n = int(input("Enter the number of integers of Bob's set: "))
                bob_set = list(int(num) for num in input("Enter the list items separated by space: ").strip().split())[
                          :n]
                bob_instance.update_set(bob_set)
                with open(bob_set_path, mode='w+') as setfile:
                    set_values = ' '.join([str(w) for w in bob_set])
                    setfile.write(set_values)
                    setfile.close()

            elif value == "exit":
                print("Good bye!")
                break
            else:
                print("Usage commands:\n\tcontinue (it restores the last session)\n\tnew set (Gives you the "
                      "possibility to type a new bob's set\n\texit (Exit from the program)\n")

    else:
        print("Good bye!")


def main(
    party,
    operation,
    oblivious_transfer=True,
    print_mode="circuit",
):
    global bob_instance
    global bob_set_path

    if party == "alice":
        circuits = {}
        if operation == 0:
            circuits["filename"] = "set_sum.json"
            circuits["id_name"] = "set_sum"
            circuits["circuit_name"] = "set_sum"
        elif operation == 1:
            circuits["filename"] = "set_cmp.json"
            circuits["id_name"] = "set_cmp"
            circuits["circuit_name"] = "set_cmp"

        n = int(input("Enter the number of integers of Alice's set: "))
        alice_set = list(int(num) for num in input("Enter the list items separated by space: ").strip().split())[:n]
        save_set_to_file("alice", alice_set)
        # start process Yao's protocol
        alice = Alice(circuits, alice_set, oblivious_transfer=oblivious_transfer, print_mode=print_mode,
                      operation=operation)
        alice.start()
    elif party == "bob":
        atexit.register(go_to_dev_mode)  # the listener for the Ctrl-C termination sequence

        n = int(input("Enter the number of integers of Bob's set: "))
        bob_set = list(int(num) for num in input("Enter the list items separated by space: ").strip().split())[:n]
        bob_set_path = save_set_to_file("bob", bob_set)
        bob = Bob(bob_set, oblivious_transfer=oblivious_transfer)
        bob_instance = bob
        bob.listen()


    else:
        print(f"[ERROR] Unknown party '{party}'")


if __name__ == '__main__':
    import argparse

    def init():

        parser = argparse.ArgumentParser(description="Run Yao protocol.")
        parser.add_argument("party",
                            choices=["alice", "bob"],
                            help="the yao party to run")

        parser.add_argument(
            "-o",
            "--operation",
            metavar="mode",
            choices=["0", "1"],
            default="0",
            help="The operation they want to compute: set sum or compare set values"
        )

        parser.add_argument(
            "-m",
            metavar="mode",
            choices=["circuit", "table"],
            default="circuit",
            help="the print mode for tests (default 'circuit')")

        main(
                party=parser.parse_args().party,
                operation=int(parser.parse_args().operation),
                print_mode=parser.parse_args().m
            )


    init()
