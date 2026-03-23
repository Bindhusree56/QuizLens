// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract QuizLens {
    struct Record {
        bool valid;
        address setter;
        bytes32 reportHash;
        uint256 timestamp;
        string title;
    }

    mapping(bytes32 => Record) private records;
    bytes32 public merkleRoot;          // ← new: store current root on-chain
    bytes32[] public notarizedHashes;   // ← new: all leaf hashes

    event Notarized(bytes32 indexed paperHash, address indexed setter, string title);
    event MerkleRootUpdated(bytes32 newRoot);

    function notarize(bytes32 paperHash, bytes32 reportHash, string calldata title) external {
        records[paperHash] = Record(true, msg.sender, reportHash, block.timestamp, title);
        notarizedHashes.push(paperHash);
        merkleRoot = computeRoot();         // ← recompute root after each notarize
        emit Notarized(paperHash, msg.sender, title);
        emit MerkleRootUpdated(merkleRoot);
    }

    function verifyMerkleProof(
        bytes32 leaf,
        bytes32[] calldata proof,
        bytes32 side           // 0 = sibling is on right, 1 = sibling is on left
    ) external view returns (bool) {
        bytes32 computed = leaf;
        for (uint i = 0; i < proof.length; i++) {
            computed = side == 0
                ? keccak256(abi.encodePacked(computed, proof[i]))
                : keccak256(abi.encodePacked(proof[i], computed));
        }
        return computed == merkleRoot;
    }

    function computeRoot() internal view returns (bytes32) {
        uint n = notarizedHashes.length;
        if (n == 0) return bytes32(0);
        bytes32[] memory layer = new bytes32[](n);
        for (uint i = 0; i < n; i++) layer[i] = notarizedHashes[i];
        while (layer.length > 1) {
            uint len = layer.length;
            uint newLen = (len + 1) / 2;
            bytes32[] memory next = new bytes32[](newLen);
            for (uint i = 0; i < newLen; i++) {
                uint left = i * 2;
                uint right = left + 1 < len ? left + 1 : left;
                next[i] = keccak256(abi.encodePacked(layer[left], layer[right]));
            }
            layer = next;
        }
        return layer[0];
    }

    function verify(bytes32 paperHash) external view returns (
        bool valid, address setter, bytes32 reportHash, uint256 timestamp, string memory title
    ) {
        Record storage r = records[paperHash];
        return (r.valid, r.setter, r.reportHash, r.timestamp, r.title);
    }

    function getLeafCount() external view returns (uint256) {
        return notarizedHashes.length;
    }
}