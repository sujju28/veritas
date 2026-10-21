// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title RulesetRegistry
/// @notice Stores canonical ruleset manifest digests on a local Anvil chain.
/// @dev key = sha256("VERITAS:RULESET:" || version).
///      Same hash is a no-op. A different hash for the same key reverts.
contract RulesetRegistry {
    struct Entry {
        bool exists;
        bytes32 manifestSha256;
        bool deprecated;
        address sender;
        uint64 blockNumber;
        uint64 timestamp;
    }

    address public admin;
    mapping(bytes32 => Entry) private rulesets;

    event RulesetRegistered(
        bytes32 indexed key,
        bytes32 manifestSha256,
        address indexed sender,
        uint256 blockNumber
    );
    event RulesetDeprecated(
        bytes32 indexed key,
        address indexed sender,
        uint256 blockNumber
    );

    error ZeroKey();
    error ZeroDigest();
    error NotAdmin();
    error ManifestMismatch(bytes32 storedDigest, bytes32 submittedDigest);
    error RulesetNotFound(bytes32 key);

    constructor() {
        admin = msg.sender;
    }

    function register(bytes32 key, bytes32 manifestSha256) external {
        if (msg.sender != admin) revert NotAdmin();
        if (key == bytes32(0)) revert ZeroKey();
        if (manifestSha256 == bytes32(0)) revert ZeroDigest();

        Entry storage existing = rulesets[key];
        if (existing.exists) {
            if (existing.manifestSha256 != manifestSha256) {
                revert ManifestMismatch(existing.manifestSha256, manifestSha256);
            }
            return;
        }

        rulesets[key] = Entry({
            exists: true,
            manifestSha256: manifestSha256,
            deprecated: false,
            sender: msg.sender,
            blockNumber: uint64(block.number),
            timestamp: uint64(block.timestamp)
        });
        emit RulesetRegistered(key, manifestSha256, msg.sender, block.number);
    }

    function deprecate(bytes32 key) external {
        if (msg.sender != admin) revert NotAdmin();
        if (key == bytes32(0)) revert ZeroKey();

        Entry storage existing = rulesets[key];
        if (!existing.exists) revert RulesetNotFound(key);
        if (existing.deprecated) return;

        existing.deprecated = true;
        emit RulesetDeprecated(key, msg.sender, block.number);
    }

    function getRuleset(bytes32 key)
        external
        view
        returns (
            bool exists,
            bytes32 manifestSha256,
            bool deprecated,
            address sender,
            uint64 blockNumber,
            uint64 timestamp
        )
    {
        Entry storage item = rulesets[key];
        return (
            item.exists,
            item.manifestSha256,
            item.deprecated,
            item.sender,
            item.blockNumber,
            item.timestamp
        );
    }
}
