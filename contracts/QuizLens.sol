// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title  QuizLens
 * @notice Immutable on-chain audit trail for exam paper pre-vetting.
 *         Stores (paperHash, reportHash) before the exam runs so
 *         accreditors can prove the paper was analysed and unchanged.
 */
contract QuizLens {

    struct Record {
        address setter;       // wallet of the exam setter
        bytes32 paperHash;    // SHA-256 of raw question paper
        bytes32 reportHash;   // SHA-256 of NLP analysis report PDF
        uint256 timestamp;    // block.timestamp at notarization
        string  title;        // human-readable exam title
        bool    exists;
    }

    // paperHash → Record
    mapping(bytes32 => Record) private _records;

    // setter wallet → list of paper hashes they submitted
    mapping(address => bytes32[]) private _setterPapers;

    // ── Events ────────────────────────────────────────────
    event PaperNotarized(
        bytes32 indexed paperHash,
        bytes32 indexed reportHash,
        address indexed setter,
        string  title,
        uint256 timestamp
    );

    // ── Errors ────────────────────────────────────────────
    error AlreadyNotarized(bytes32 paperHash);
    error ZeroHash();

    // ── Write ─────────────────────────────────────────────
    /**
     * @param paperHash  SHA-256 of the question paper file (bytes32)
     * @param reportHash SHA-256 of the NLP analysis report (bytes32)
     * @param title      Human-readable exam title
     */
    function notarize(
        bytes32 paperHash,
        bytes32 reportHash,
        string calldata title
    ) external {
        if (paperHash == bytes32(0) || reportHash == bytes32(0))
            revert ZeroHash();
        if (_records[paperHash].exists)
            revert AlreadyNotarized(paperHash);

        _records[paperHash] = Record({
            setter:     msg.sender,
            paperHash:  paperHash,
            reportHash: reportHash,
            timestamp:  block.timestamp,
            title:      title,
            exists:     true
        });

        _setterPapers[msg.sender].push(paperHash);

        emit PaperNotarized(paperHash, reportHash, msg.sender, title, block.timestamp);
    }

    // ── Read ──────────────────────────────────────────────
    /**
     * @notice Verify a paper against the on-chain record.
     * @return valid       true if the paper has been notarized
     * @return setter      wallet address of the original submitter
     * @return reportHash  the NLP report hash stored at notarization
     * @return timestamp   Unix timestamp of notarization
     * @return title       exam title
     */
    function verify(bytes32 paperHash)
        external view
        returns (
            bool    valid,
            address setter,
            bytes32 reportHash,
            uint256 timestamp,
            string  memory title
        )
    {
        Record storage r = _records[paperHash];
        return (r.exists, r.setter, r.reportHash, r.timestamp, r.title);
    }

    /**
     * @notice Get all paper hashes submitted by a specific setter.
     */
    function getSetterPapers(address setter)
        external view
        returns (bytes32[] memory)
    {
        return _setterPapers[setter];
    }
}
