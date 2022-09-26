import os

"""
IMPORTANT: don't move this script 
"""

"""
:param bit_number: the number of bits involved in the operation
:param start_index: the first id of the input
"""
def addition(bits_number, start_index=1):
    index = start_index
    # creating the circuit
    step = bits_number
    gates = []
    alice = []
    bob = []
    outputs = []

    for i in range(0, bits_number):
        alice.append(index)
        index += 1

    for i in range(0, bits_number):
        bob.append(index)
        index += 1

    carry_index = None

    for i in range(1, bits_number+1):
        if i == 1:
            # we don't have the carry
            gates.append({"id": index, "type": "XOR", "in": [i, i+step]})
            outputs.append(index)  # saving output
            index += 1
            gates.append({"id": index, "type": "AND", "in": [i, i+step]})
            carry_index = index
            if bits_number == i:
                outputs.append(carry_index)
            index += 1

        else:
            # we have the carry
            gates.append({"id": index, "type": "XOR", "in": [i, i + step]})
            xor_result = index
            index += 1
            gates.append({"id": index, "type": "AND", "in": [i, i + step]})
            and_result_1 = index
            index += 1
            gates.append({"id": index, "type": "XOR", "in": [xor_result, carry_index]})
            outputs.append(index)  # save output
            index += 1
            gates.append({"id": index, "type": "AND", "in": [xor_result, carry_index]})
            and_result_2 = index
            index += 1
            gates.append({"id": index, "type": "OR", "in": [and_result_1, and_result_2]})
            carry_index = index
            index += 1
            if bits_number == i:
                outputs.append(carry_index)

    return alice, bob, outputs, gates


"""
:param bit_length: the number of bits involved in the operation
:param alice_set_cardinality: the number of values of alice's set
"""
def compare(bit_length, alice_set_cardinality):
    b = bit_length
    k = alice_set_cardinality

    gates = []
    alice = []
    bob = []
    outputs = []

    index = 0

    for i in range(0, b*k):
        index += 1
        alice.append(index)

    for i in range(0, b):
        index += 1
        bob.append(index)

    index = index + 1  # so I can start from this index for the following loops

    equality_gates_indexes = []
    for value_index in range(k):
        not_indexes = []
        for bit_index in range(b):
            xor_index = index
            gates.append({"id": index, "type": "XOR", "in": [alice[b*value_index+bit_index], bob[bit_index]]})
            index += 1
            not_index = index
            gates.append({"id": index, "type": "NOT", "in": [xor_index]})
            not_indexes.append(not_index)
            index += 1

        and_index = not_indexes[0]
        for i in range(1, len(not_indexes)):
            gates.append({"id": index, "type": "AND", "in": [and_index, not_indexes[i]]})
            and_index = index
            index += 1

        equality_gates_indexes.append(and_index)

    ## setting equality output bit ####
    equality_index = equality_gates_indexes[0]
    for i in range(1, len(equality_gates_indexes)):
        gates.append({"id": index, "type": "OR", "in": [equality_index, equality_gates_indexes[i]]})
        equality_index = index
        index += 1

    outputs.append(equality_index)

    ## setting equal value ##
    for bit_index in range(b):
        check_gates = []
        for value_index in range(k):
            gates.append({"id": index, "type": "AND", "in": [alice[value_index*b+bit_index], equality_gates_indexes[value_index]]})
            check_gates.append(index)
            index += 1

        first_or_index = check_gates[0]
        for index_check_gate in range(1, len(check_gates)):
            gates.append({"id": index, "type": "OR", "in": [first_or_index, check_gates[index_check_gate]]})
            first_or_index = index
            index += 1

        outputs.append(first_or_index)

    return alice, bob, outputs, gates


"""
:param file_name: the name of the created file
:param bit_number: the major number of bits the circuit will have to deal with
:param name: the name of the circuit
:param id_name: the id name of the circuit
:param operation: the type of circuit you want to build (0: sum, 1: compare)
:param alice_set_cardinality: useful only if operation=1

It creates the json file that contains the circuit for the operation. The file will be saved within ./circuits
"""


def create_circuit(file_name, bit_number, name, id_name, operation=0, alice_set_cardinality=None):
    circuit = {"name": name, "circuits": [{}]}

    # cleaning the filename
    json_path = os.path.dirname(__file__)+"/circuits/"+file_name
    json_path = json_path.replace(".json", "")
    json_path = json_path + '.json'

    if operation == 0:
        alice, bob, outs, gates = addition(bit_number, 1)
        out = outs

        circuit["circuits"][0]["id"] = id_name
        circuit["circuits"][0]["alice"] = alice
        circuit["circuits"][0]["bob"] = bob
        circuit["circuits"][0]["out"] = out
        circuit["circuits"][0]["gates"] = gates

        circuit_string = str(circuit).replace('\'', '"')

        with open(json_path, mode='w+') as json_file:  # create file if not exists
            json_file.write(circuit_string)
            json_file.close()

    if operation == 1:
        alice, bob, outs, gates = compare(bit_number, alice_set_cardinality)
        out = outs

        circuit["circuits"][0]["id"] = id_name
        circuit["circuits"][0]["alice"] = alice
        circuit["circuits"][0]["bob"] = bob
        circuit["circuits"][0]["out"] = out
        circuit["circuits"][0]["gates"] = gates

        circuit_string = str(circuit).replace('\'', '"')

        with open(json_path, mode='w+') as json_file:  # create file if not exists
            json_file.write(circuit_string)
            json_file.close()

    return json_path


"""
How to call the method:
> create_circuit(file_name, num_bits, name, id_name, operation (optional), alice_set_cardinality (optional))
"""



