#!/usr/bin/env python3
"""Mutation testing of `cvx-vault-v1` (gate Q-07, docs/TESTING.md): the share
registry (mutants R
and T), the conversion functions of docs/MATH.md section 7 (mutants C) and
the vault of docs/SPEC.md sections 4 and 5 (mutants V).

Each mutant is a set of exact source replacements in the package: it removes
or weakens one guard, moves one bound or time boundary, drops one archive,
widens one set of actors, changes one order, swaps a rounding direction or
an operand, or changes a virtual term or the offset exponent. For each, the
script copies the package, its test package and the vendored DARs into a
scratch workspace, applies the mutant, builds the package, runs `dpm test`
on the test package and records the tests that fail. A mutant is killed
when the build of the package or of the tests fails, when at least one test
fails, or when the run exceeds its time limit; it survives when every test
passes. The unmutated tree is run first and must pass. The structure follows
scripts/mutate-math.py. The package's dependencies on `cvx-vault-math-v1`
and `cvx-api-vault-v1` are copied from their build outputs, which must exist.

The repository tree is never modified. Mutants left out as equivalent are
recorded in EQUIVALENT, with the argument for each, and printed with every
run.

Usage: scripts/mutate-registry.py [--sdk 3.4.11] [--only R001,R002] [--prefix C] [--jobs 4] [--timeout 900]
                                  [--check-only]
                                  [--log-dir DIR]   (keeps each mutant's test output as DIR/<id>.txt)
Exit status: 0 when no mutant survives and the baseline passes; 1 otherwise.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "packages/token/vault-v1"
TEST = "test/vault-v1-test"
VENDOR = "dars/vendor"
SR = f"{PKG}/daml/Cayvox/VaultV1/Internal/ShareRegistry.daml"
TS = f"{PKG}/daml/Cayvox/VaultV1/Internal/TokenStandard.daml"
CP = f"{PKG}/daml/Cayvox/VaultV1/Conversion.daml"
CI = f"{PKG}/daml/Cayvox/VaultV1/Internal/Conversion.daml"
FA = f"{PKG}/daml/Cayvox/VaultV1/Internal/Failure.daml"
VV = f"{PKG}/daml/Cayvox/VaultV1.daml"
IV = f"{PKG}/daml/Cayvox/VaultV1/Internal/Vault.daml"
DEP_DARS = ["packages/utils/vault-math-v1/.daml/dist", "packages/token/api-vault-v1/.daml/dist"]

LT_IMPORT = ("import DA.Time (isLedgerTimeLT)", "import DA.Time (isLedgerTimeLT, isLedgerTimeLE)")
GT_IMPORT = ("import DA.Time (isLedgerTimeGT)", "import DA.Time (isLedgerTimeGT, isLedgerTimeGE)")

# (id, area, description, file, [(old, new), ...]). Each `old` must occur
# exactly once in the file.
MUTANTS = [
    # Input holdings (RM-04, RM-09; T-06).
    ("R001", "guard", "input holding: instrument not checked", SR,
     [("(holding.instrumentId == instrumentId && holding.account == account && inputHoldingUsable now holding)",
       "(holding.account == account && inputHoldingUsable now holding)")]),
    ("R002", "guard", "input holding: account not checked", SR,
     [("(holding.instrumentId == instrumentId && holding.account == account && inputHoldingUsable now holding)",
       "(holding.instrumentId == instrumentId && inputHoldingUsable now holding)")]),
    ("R003", "guard", "input holding: lock not checked", SR,
     [("(holding.instrumentId == instrumentId && holding.account == account && inputHoldingUsable now holding)",
       "(holding.instrumentId == instrumentId && holding.account == account)")]),
    ("R004", "boundary", "expired lock: expiry exclusive instead of inclusive", SR,
     [("Some expiresAt -> now >= expiresAt", "Some expiresAt -> now > expiresAt")]),
    ("R005", "guard", "a lock without expiry is usable", SR,
     [("    None -> False\n\n-- | Read the caller's", "    None -> True\n\n-- | Read the caller's")]),
    ("R006", "guard", "transfer inputs read and archived through the interface, not the template (T-06)", SR,
     [("    holding <- fetch shareCid\n",
       "    holding <- (\\v -> ShareHolding with admin = v.instrumentId.admin; instrumentId = v.instrumentId; "
       "account = v.account; amount = v.amount; lock = v.lock; lockObservers = []; meta = v.meta) . view <$> fetch cid\n"),
      ("  forA_ inputCids archive\n", "  forA_ inputCids (archive . toInterfaceContractId @Holding)\n")]),

    # Event log (RM-44 to RM-48; T-12).
    ("R010", "archival", "event log not consumed by its event", SR,
     [("        archive (fromInterfaceContractId @ShareEventLog self)\n", "")]),
    ("R011", "guard", "event log: admin not checked", SR,
     [("        require registryWrongAdmin (arg.admin == admin)\n", "")]),
    ("R012", "guard", "event log: account not checked", SR,
     [("        require registryInvalidAccount (arg.account == account)\n", "")]),
    ("R013", "guard", "event log: observers not checked", SR,
     [("        require registryUnauthorizedActors (all (`elem` arg.observers) (accountParties admin account))\n", "")]),

    # Allocation_Settle (RM-24 to RM-27).
    ("R020", "archival", "settle: allocation not archived", SR,
     [("        archive (fromInterfaceContractId @ShareAllocation self)\n        checkActors arg.actors [admin :: settlement.executors]",
       "        checkActors arg.actors [admin :: settlement.executors]")]),
    ("R021", "authority", "settle: executors without the admin accepted", SR,
     [("checkActors arg.actors [admin :: settlement.executors]",
       "checkActors arg.actors [admin :: settlement.executors, settlement.executors]")]),
    ("R022", "guard", "settle: iteration arguments not checked", SR,
     [("        validateNextIterationArgs False arg.extraTransferLegSides arg.nextIterationFunding\n", "")]),
    ("R023", "guard", "settle: deadline not checked", SR,
     [("          open <- isLedgerTimeLT deadline\n          require registryDeadlinePassed open\n        -- The `ensure` lets",
       "          open <- isLedgerTimeLT deadline\n          require registryDeadlinePassed (open || True)\n        -- The `ensure` lets")]),
    ("R024", "boundary", "settle: allowed at the deadline", SR,
     [LT_IMPORT,
      ("          open <- isLedgerTimeLT deadline\n          require registryDeadlinePassed open\n        -- The `ensure` lets",
       "          open <- isLedgerTimeLE deadline\n          require registryDeadlinePassed open\n        -- The `ensure` lets")]),
    ("R025", "archival", "settle: locked holding not archived", SR,
     [("Some cid -> archive cid >> pure [cid]", "Some cid -> pure [cid]")]),
    ("R027", "guard", "settle: settlement event not logged", SR,
     [("        logAllocationSettlement emitEvent (map toInterfaceContractId inputs) allocation (map toInterfaceContractId outputs)\n",
       "")]),

    # Allocation_Cancel and Allocation_Withdraw (RM-25, RM-28 to RM-30).
    ("R030", "archival", "cancel: allocation not archived", SR,
     [("        archive (fromInterfaceContractId @ShareAllocation self)\n        cancelAllocation",
       "        cancelAllocation")]),
    ("R031", "archival", "withdraw: allocation not archived", SR,
     [("        archive (fromInterfaceContractId @ShareAllocation self)\n        withdrawAllocation",
       "        withdrawAllocation")]),
    ("R032", "archival", "unlock: locked holding not archived", SR,
     [("    locked <- fetch lockedCid\n    archive lockedCid\n", "    locked <- fetch lockedCid\n")]),
    ("R033", "guard", "unlock: release not logged", SR,
     [("    logMergeSplit this.admin this.allocation.authorizer [lockedCid] reason [released]\n", "")]),

    # Transfer instructions (RM-08, RM-15, RM-17 to RM-19).
    ("R040", "archival", "accept: instruction not archived", SR,
     [("        archive (fromInterfaceContractId @ShareTransferInstruction self)\n        checkActors arg.actors (actorGroups False admin transfer.receiver)",
       "        checkActors arg.actors (actorGroups False admin transfer.receiver)")]),
    ("R041", "authority", "accept: the receiver's provider alone accepts", SR,
     [("checkActors arg.actors (actorGroups False admin transfer.receiver)",
       "checkActors arg.actors (actorGroups True admin transfer.receiver)")]),
    ("R042", "guard", "accept: executeBefore not checked", SR,
     [("        open <- isLedgerTimeLT transfer.executeBefore\n        require registryDeadlinePassed open\n        archive lockedHoldingCid",
       "        archive lockedHoldingCid")]),
    ("R043", "boundary", "accept: allowed at executeBefore", SR,
     [LT_IMPORT,
      ("        open <- isLedgerTimeLT transfer.executeBefore\n        require registryDeadlinePassed open\n        archive lockedHoldingCid",
       "        open <- isLedgerTimeLE transfer.executeBefore\n        require registryDeadlinePassed open\n        archive lockedHoldingCid")]),
    ("R044", "archival", "accept: locked holding not archived", SR,
     [("        require registryDeadlinePassed open\n        archive lockedHoldingCid\n",
       "        require registryDeadlinePassed open\n")]),
    ("R045", "archival", "reject: instruction not archived", SR,
     [("        archive (fromInterfaceContractId @ShareTransferInstruction self)\n        checkActors arg.actors (actorGroups True admin transfer.receiver)",
       "        checkActors arg.actors (actorGroups True admin transfer.receiver)")]),
    ("R046", "authority", "reject: the sender's parties reject", SR,
     [("checkActors arg.actors (actorGroups True admin transfer.receiver)",
       "checkActors arg.actors (actorGroups True admin transfer.sender)")]),
    ("R047", "archival", "withdraw transfer: instruction not archived", SR,
     [("        archive (fromInterfaceContractId @ShareTransferInstruction self)\n        checkActors arg.actors (actorGroups True admin transfer.sender)",
       "        checkActors arg.actors (actorGroups True admin transfer.sender)")]),
    ("R048", "authority", "withdraw transfer: the receiver's parties withdraw", SR,
     [("checkActors arg.actors (actorGroups True admin transfer.sender)",
       "checkActors arg.actors (actorGroups True admin transfer.receiver)")]),
    ("R049", "archival", "return to sender: locked holding not archived", SR,
     [("  archive this.lockedHoldingCid\n", "")]),
    ("R050", "authority", "actor groups: the provider alone may always act", SR,
     [("[[principal], [principal, provider]] ++ [[provider] | providerAlone]",
       "[[principal], [principal, provider], [provider]]")]),

    # SettlementFactory_SettleBatch in the rules (RM-34; T-06).
    ("R060", "guard", "settle batch: leg instrument not checked", SR,
     [("        forA_ arg.transferLegs $ \\leg -> require registryWrongInstrument (leg.instrumentId == instrumentId.id)\n", "")]),
    ("R061", "guard", "settle batch: allocation instrument not checked", SR,
     [("  require registryWrongInstrument (shareAllocation.instrumentId == instrumentId)\n", "")]),
    ("R062", "guard", "settle batch: allocations read through the interface, not the template (T-06)", SR,
     [("  shareAllocation <- fetch (fromInterfaceContractId @ShareAllocation cid)\n"
       "  require registryWrongInstrument (shareAllocation.instrumentId == instrumentId)\n"
       "  pure (view (toInterface @Allocation shareAllocation))",
       "  allocation <- fetch cid\n  pure (view allocation)")]),

    # Accounts.
    ("R070", "guard", "account: identifier length not checked", SR,
     [("  require registryFieldTooLarge (boundedAccount account)\n", "")]),
    ("R071", "guard", "account: special accounts allowed everywhere", SR,
     [("(isRegularAccount admin account || (allowSpecial && isSpecialAccount account))",
       "(isRegularAccount admin account || isSpecialAccount account)")]),
    ("R072", "guard", "account: any account allowed where special ones are", SR,
     [("(isRegularAccount admin account || (allowSpecial && isSpecialAccount account))",
       "(isRegularAccount admin account || allowSpecial)")]),
    ("R073", "guard", "regular account: the admin may own shares (T-13)", SR,
     [("isRegularAccount admin account = isSome account.owner && account.owner /= Some admin",
       "isRegularAccount admin account = isSome account.owner")]),
    ("R074", "guard", "special account: only the mint account recognised", SR,
     [("isSpecialAccount account = account == mintAccount || account == burnAccount",
       "isSpecialAccount account = account == mintAccount")]),

    # AllocationFactory_Allocate (RM-40 to RM-42, RM-22, RM-56).
    ("R080", "guard", "allocate: admin not checked", SR,
     [("  require registryWrongAdmin (spec.admin == admin)\n", "")]),
    ("R081", "guard", "allocate: authorizer account not checked", SR,
     [("  validateAccount admin True authorizer\n", "")]),
    ("R082", "authority", "allocate: the provider alone allocates", SR,
     [("  checkActors arg.actors (actorGroups False admin authorizer)\n",
       "  checkActors arg.actors (actorGroups True admin authorizer)\n")]),
    ("R083", "guard", "allocate: actors not checked", SR,
     [("  checkActors arg.actors (actorGroups False admin authorizer)\n", "")]),
    ("R084", "guard", "allocate: requestedAt not checked", SR,
     [("  notYet <- isLedgerTimeLT arg.requestedAt\n  require registryNotYetRequested (not notYet)\n", "")]),
    ("R085", "boundary", "allocate: requestedAt at the ledger time rejected", SR,
     [LT_IMPORT,
      ("  notYet <- isLedgerTimeLT arg.requestedAt\n", "  notYet <- isLedgerTimeLE arg.requestedAt\n")]),
    ("R086", "guard", "allocate: settlement and metadata sizes not checked", SR,
     [("  require registryFieldTooLarge (boundedSettlement arg.settlement && boundedMeta spec.meta)\n", "")]),
    ("R087", "guard", "allocate: empty leg sides accepted", SR,
     [("  require registryNoTransferLegs (not (null spec.transferLegSides))\n", "")]),
    ("R088", "guard", "allocate: leg count and sizes not checked", SR,
     [("  require registryFieldTooLarge (length spec.transferLegSides <= maxLegs && all boundedLegSide spec.transferLegSides)\n", "")]),
    ("R089", "guard", "allocate: leg amount not checked", SR,
     [("    require registryInvalidAmount (leg.amount > 0.0)\n", "")]),
    ("R090", "boundary", "allocate: zero leg amount accepted", SR,
     [("    require registryInvalidAmount (leg.amount > 0.0)\n", "    require registryInvalidAmount (leg.amount >= 0.0)\n")]),
    ("R091", "guard", "allocate: leg instrument not checked", SR,
     [("    require registryWrongInstrument (leg.instrumentId == rules.instrumentId.id)\n", "")]),
    ("R092", "guard", "allocate: other side not checked", SR,
     [("    validateAccount admin True leg.otherside\n", "")]),
    ("R093", "guard", "allocate: side of a special account not checked", SR,
     [("    require registryInvalidAccount (sideAllowed authorizer leg.side)\n", "")]),
    ("R094", "guard", "allocate: mint account may receive", SR,
     [("  | authorizer == mintAccount = side == SenderSide", "  | authorizer == mintAccount = True")]),
    ("R095", "guard", "allocate: burn account may send", SR,
     [("  | authorizer == burnAccount = side == ReceiverSide", "  | authorizer == burnAccount = True")]),
    ("R096", "guard", "allocate: duplicate leg sides accepted", SR,
     [("  require registryDuplicateLeg\n    (Set.size (Set.fromList [ (leg.transferLegId, leg.side) | leg <- spec.transferLegSides ]) == length spec.transferLegSides)\n", "")]),
    ("R097", "guard", "allocate: iterated settlement accepted", SR,
     [("  require registryIteratedSettlement (isNone spec.nextIterationFunding)\n", "")]),
    ("R108", "guard", "allocate: committed allocation without a deadline accepted", SR,
     [("  require registryCommittedWithoutDeadline (not spec.committed || isSome spec.settlementDeadline)\n", "")]),
    ("R098", "guard", "allocate: settlement deadline not checked", SR,
     [("    open <- isLedgerTimeLT deadline\n    require registryDeadlinePassed open\n  let needed",
       "    open <- isLedgerTimeLT deadline\n    require registryDeadlinePassed (open || True)\n  let needed")]),
    ("R099", "boundary", "allocate: allowed at the settlement deadline", SR,
     [LT_IMPORT,
      ("    open <- isLedgerTimeLT deadline\n    require registryDeadlinePassed open\n  let needed",
       "    open <- isLedgerTimeLE deadline\n    require registryDeadlinePassed open\n  let needed")]),
    ("R100", "guard", "allocate: funds not checked", SR,
     [("        require registryInsufficientFunds (total >= needed)\n", "")]),
    ("R101", "boundary", "allocate: exact funds rejected", SR,
     [("        require registryInsufficientFunds (total >= needed)\n", "        require registryInsufficientFunds (total > needed)\n")]),
    ("R102", "archival", "allocate: inputs not archived", SR,
     [("        forA_ inputs $ \\(cid, _) -> archive cid\n", "")]),
    ("R103", "boundary", "allocate: change created when funds are exact", SR,
     [("        change <- if total > needed\n", "        change <- if total >= needed\n")]),
    ("R104", "guard", "allocate: inputs not validated when no funds are needed", SR,
     [("    if needed == 0.0\n", "    if True\n")]),
    ("R105", "guard", "allocate: lock not logged", SR,
     [("        logMergeSplit admin authorizer (map fst inputs) \"allocate\" (locked :: change)\n", "")]),
    ("R106", "authority", "allocate: executors do not observe the locked holding", SR,
     [("          (\"allocation \" <> arg.settlement.id) arg.settlement.executors\n",
       "          (\"allocation \" <> arg.settlement.id) []\n")]),

    # TransferFactory_Transfer (RM-06 to RM-14).
    ("R110", "guard", "transfer: admin not checked", SR,
     [("  require registryWrongAdmin (transfer.instrumentId.admin == admin)\n", "")]),
    ("R111", "guard", "transfer: instrument not checked", SR,
     [("  require registryWrongInstrument (transfer.instrumentId == rules.instrumentId)\n", "")]),
    ("R112", "guard", "transfer: sender account not checked", SR,
     [("  validateAccount admin False transfer.sender\n", "")]),
    ("R113", "guard", "transfer: receiver account not checked", SR,
     [("  validateAccount admin False transfer.receiver\n", "")]),
    ("R114", "authority", "transfer: the sender's owner need not act", SR,
     [("    (senderOwner `elem` arg.actors && all (`elem` allowed) arg.actors)",
       "    (all (`elem` allowed) arg.actors)")]),
    ("R115", "authority", "transfer: outsiders may act", SR,
     [("    (senderOwner `elem` arg.actors && all (`elem` allowed) arg.actors)",
       "    (senderOwner `elem` arg.actors)")]),
    ("R116", "guard", "transfer: sizes not checked", SR,
     [("  require registryFieldTooLarge (boundedTransfer transfer)\n", "")]),
    ("R117", "guard", "transfer: amount not checked", SR,
     [("  require registryInvalidAmount (transfer.amount > 0.0)\n", "")]),
    ("R118", "boundary", "transfer: zero amount accepted", SR,
     [("  require registryInvalidAmount (transfer.amount > 0.0)\n", "  require registryInvalidAmount (transfer.amount >= 0.0)\n")]),
    ("R119", "guard", "transfer: requestedAt not checked", SR,
     [("  notYet <- isLedgerTimeLT transfer.requestedAt\n  require registryNotYetRequested (not notYet)\n", "")]),
    ("R120", "boundary", "transfer: requestedAt at the ledger time rejected", SR,
     [LT_IMPORT, ("  notYet <- isLedgerTimeLT transfer.requestedAt\n", "  notYet <- isLedgerTimeLE transfer.requestedAt\n")]),
    ("R121", "guard", "transfer: executeBefore not checked", SR,
     [("  open <- isLedgerTimeLT transfer.executeBefore\n  require registryDeadlinePassed open\n", "")]),
    ("R122", "boundary", "transfer: allowed at executeBefore", SR,
     [LT_IMPORT, ("  open <- isLedgerTimeLT transfer.executeBefore\n  require registryDeadlinePassed open\n",
                  "  open <- isLedgerTimeLE transfer.executeBefore\n  require registryDeadlinePassed open\n")]),
    ("R123", "guard", "transfer: funds not checked", SR,
     [("  require registryInsufficientFunds (total >= transfer.amount)\n", "")]),
    ("R124", "boundary", "transfer: exact funds rejected", SR,
     [("  require registryInsufficientFunds (total >= transfer.amount)\n", "  require registryInsufficientFunds (total > transfer.amount)\n")]),
    ("R125", "archival", "transfer: inputs not archived", SR,
     [("  forA_ inputCids archive\n", "")]),
    ("R126", "boundary", "transfer: change created when funds are exact", SR,
     [("  change <- if total > transfer.amount\n", "  change <- if total >= transfer.amount\n")]),
    ("R127", "guard", "transfer: never completes in one step", SR,
     [("      oneStep = receiverOwner `elem` arg.actors\n", "      oneStep = False\n")]),
    ("R128", "guard", "transfer: always completes in one step", SR,
     [("      oneStep = receiverOwner `elem` arg.actors\n", "      oneStep = True\n")]),
    ("R129", "authority", "transfer: the receiver does not observe the locked holding", SR,
     [("        \"transfer\" (accountParties admin transfer.receiver)\n", "        \"transfer\" []\n")]),
    ("R130", "guard", "transfer: events not logged", SR,
     [("      logTransfer admin transfer inputCids change [received]\n", "")]),

    # Template preconditions (T-13, T-16).
    ("R140", "guard", "holding: zero amount accepted", SR,
     [("    ensure amount > 0.0\n      && instrumentId.admin == admin", "    ensure amount >= 0.0\n      && instrumentId.admin == admin")]),
    ("R141", "guard", "holding: another admin's instrument accepted", SR,
     [("      && instrumentId.admin == admin && boundedText instrumentId.id\n      && isRegularAccount admin account && boundedAccount account",
       "      && boundedText instrumentId.id\n      && isRegularAccount admin account && boundedAccount account")]),
    ("R142", "guard", "holding: special or admin accounts accepted (T-13)", SR,
     [("      && isRegularAccount admin account && boundedAccount account\n      && optional True boundedLock lock",
       "      && boundedAccount account\n      && optional True boundedLock lock")]),
    ("R143", "guard", "holding: account identifier unbounded", SR,
     [("      && isRegularAccount admin account && boundedAccount account\n      && optional True boundedLock lock",
       "      && isRegularAccount admin account\n      && optional True boundedLock lock")]),
    ("R144", "guard", "holding: lock unchecked", SR,
     [("      && optional True boundedLock lock\n", "")]),
    ("R145", "guard", "holding: lock observers without a lock", SR,
     [("      && (isSome lock || null lockObservers) && length lockObservers <= maxExecutors + 2",
       "      && length lockObservers <= maxExecutors + 2")]),
    ("R146", "bound", "holding: lock observers unbounded", SR,
     [("      && (isSome lock || null lockObservers) && length lockObservers <= maxExecutors + 2",
       "      && (isSome lock || null lockObservers)")]),
    ("R147", "bound", "holding: one more lock observer", SR,
     [("length lockObservers <= maxExecutors + 2", "length lockObservers <= maxExecutors + 3")]),
    ("R148", "bound", "holding: one fewer lock observer", SR,
     [("length lockObservers <= maxExecutors + 2", "length lockObservers <= maxExecutors + 1")]),
    ("R149", "guard", "holding: metadata unbounded", SR,
     [("      && boundedMeta meta\n\n    interface instance Holding", "\n    interface instance Holding")]),
    ("R150", "guard", "lock: holders may be empty", SR,
     [("  not (null lock.holders) && length lock.holders <= maxExecutors", "  length lock.holders <= maxExecutors")]),
    ("R151", "guard", "lock: duplicate holders", SR,
     [("    && Set.size (Set.fromList lock.holders) == length lock.holders\n", "\n")]),
    ("R152", "guard", "lock: context unbounded", SR,
     [("\n    && optional True boundedText lock.context", "")]),
    ("R153", "guard", "event log: special accounts accepted", SR,
     [("    ensure isRegularAccount admin account && boundedAccount account\n\n    interface instance Events.EventLog",
       "    ensure boundedAccount account\n\n    interface instance Events.EventLog")]),
    ("R154", "guard", "event log: account identifier unbounded", SR,
     [("    ensure isRegularAccount admin account && boundedAccount account\n\n    interface instance Events.EventLog",
       "    ensure isRegularAccount admin account\n\n    interface instance Events.EventLog")]),
    ("R155", "guard", "allocation: another admin accepted", SR,
     [("    ensure allocation.admin == admin && instrumentId.admin == admin\n", "    ensure instrumentId.admin == admin\n")]),
    ("R156", "guard", "allocation: settlement unbounded", SR,
     [("      && boundedSettlement settlement\n", "\n")]),
    ("R157", "guard", "allocation: leg list unchecked", SR,
     [("      && not (null allocation.transferLegSides) && length allocation.transferLegSides <= maxLegs\n", "\n")]),
    ("R158", "guard", "allocation: leg sides unbounded", SR,
     [("      && all boundedLegSide allocation.transferLegSides\n", "\n")]),
    ("R159", "guard", "allocation: next-iteration funding accepted", SR,
     [("      && isNone allocation.nextIterationFunding\n", "\n")]),
    ("R195", "guard", "allocation: committed without a deadline accepted", SR,
     [("      && (not allocation.committed || isSome allocation.settlementDeadline)\n", "\n")]),
    ("R196", "guard", "allocation: non-positive leg amounts accepted", SR,
     [("      && all (\\leg -> leg.amount > 0.0 && sideAllowed allocation.authorizer leg.side) allocation.transferLegSides\n",
       "      && all (\\leg -> sideAllowed allocation.authorizer leg.side) allocation.transferLegSides\n")]),
    ("R197", "guard", "allocation: a special account on the wrong side accepted", SR,
     [("      && all (\\leg -> leg.amount > 0.0 && sideAllowed allocation.authorizer leg.side) allocation.transferLegSides\n",
       "      && all (\\leg -> leg.amount > 0.0) allocation.transferLegSides\n")]),
    ("R198", "guard", "allocation: unused inputs returned unvalidated (A-04)", SR,
     [("        _ <- validateInputHoldings rules.instrumentId authorizer arg.inputHoldingCids\n        pure (None, arg.inputHoldingCids)\n", "        pure (None, arg.inputHoldingCids)\n")]),
    ("R160", "guard", "allocation: any authorizer accepted", SR,
     [("      && (isRegularAccount admin allocation.authorizer || isSpecialAccount allocation.authorizer)\n", "\n")]),
    ("R161", "guard", "allocation: authorizer and metadata unbounded", SR,
     [("      && boundedAccount allocation.authorizer && boundedMeta allocation.meta\n", "\n")]),
    ("R162", "guard", "transfer instruction: another admin's instrument accepted", SR,
     [("    ensure transfer.instrumentId.admin == admin && transfer.amount > 0.0\n",
       "    ensure transfer.amount > 0.0\n")]),
    ("R191", "guard", "transfer instruction: zero amount accepted", SR,
     [("    ensure transfer.instrumentId.admin == admin && transfer.amount > 0.0\n",
       "    ensure transfer.instrumentId.admin == admin\n")]),
    ("R192", "guard", "transfer instruction: any sender accepted", SR,
     [("      && isRegularAccount admin transfer.sender && isRegularAccount admin transfer.receiver\n",
       "      && isRegularAccount admin transfer.receiver\n")]),
    ("R193", "guard", "transfer instruction: any receiver accepted", SR,
     [("      && isRegularAccount admin transfer.sender && isRegularAccount admin transfer.receiver\n",
       "      && isRegularAccount admin transfer.sender\n")]),
    ("R194", "guard", "transfer instruction: transfer unbounded", SR,
     [("      && isRegularAccount admin transfer.sender && isRegularAccount admin transfer.receiver\n      && boundedTransfer transfer\n",
       "      && isRegularAccount admin transfer.sender && isRegularAccount admin transfer.receiver\n")]),
    ("R163", "guard", "rules: another admin's instrument accepted", SR,
     [("    ensure instrumentId.admin == admin && not (T.isEmpty instrumentId.id)", "    ensure not (T.isEmpty instrumentId.id)")]),
    ("R164", "guard", "rules: empty instrument identifier accepted", SR,
     [("    ensure instrumentId.admin == admin && not (T.isEmpty instrumentId.id)", "    ensure instrumentId.admin == admin")]),
    ("R165", "guard", "rules: metadata unbounded", SR,
     [("      && boundedMeta meta\n\n    interface instance AllocationFactory", "\n    interface instance AllocationFactory")]),

    # Bounds (T-16; RM-55, RM-56).
    ("R170", "bound", "text: 257 characters", SR, [("maxTextLength = 256", "maxTextLength = 257")]),
    ("R171", "bound", "text: 255 characters", SR, [("maxTextLength = 256", "maxTextLength = 255")]),
    ("R172", "bound", "metadata: 17 entries", SR, [("maxMetaEntries = 16", "maxMetaEntries = 17")]),
    ("R173", "bound", "metadata: 15 entries", SR, [("maxMetaEntries = 16", "maxMetaEntries = 15")]),
    ("R174", "bound", "metadata value: 1025 characters", SR, [("maxMetaValueLength = 1024", "maxMetaValueLength = 1025")]),
    ("R175", "bound", "metadata value: 1023 characters", SR, [("maxMetaValueLength = 1024", "maxMetaValueLength = 1023")]),
    ("R176", "bound", "legs: 26", SR, [("maxLegs = 25", "maxLegs = 26")]),
    ("R177", "bound", "legs: 24", SR, [("maxLegs = 25", "maxLegs = 24")]),
    ("R178", "bound", "executors: 11", SR, [("maxExecutors = 10", "maxExecutors = 11")]),
    ("R179", "bound", "executors: 9", SR, [("maxExecutors = 10", "maxExecutors = 9")]),
    ("R180", "bound", "inputs: 51", SR, [("maxInputs = 50", "maxInputs = 51")]),
    ("R181", "bound", "inputs: 49", SR, [("maxInputs = 50", "maxInputs = 49")]),
    ("R182", "bound", "metadata keys unbounded", SR,
     [("all (\\(k, v) -> boundedText k && T.length v <= maxMetaValueLength) entries",
       "all (\\(_, v) -> T.length v <= maxMetaValueLength) entries")]),
    ("R183", "bound", "leg side: identifier unbounded", SR,
     [("  boundedText leg.transferLegId && boundedAccount leg.otherside", "  boundedAccount leg.otherside")]),
    ("R184", "bound", "leg side: metadata unbounded", SR,
     [("boundedText leg.instrumentId && boundedMeta leg.meta", "boundedText leg.instrumentId")]),
    ("R185", "bound", "settlement: executors may be empty", SR,
     [("  not (null settlement.executors) && length settlement.executors <= maxExecutors", "  length settlement.executors <= maxExecutors")]),
    ("R186", "bound", "settlement: identifier unbounded", SR,
     [("    && boundedText settlement.id && boundedMeta settlement.meta", "    && boundedMeta settlement.meta")]),
    ("R187", "bound", "settlement: metadata unbounded", SR,
     [("    && boundedText settlement.id && boundedMeta settlement.meta", "    && boundedText settlement.id")]),
    ("R188", "bound", "transfer: receiver identifier unbounded", SR,
     [("  boundedAccount transfer.sender && boundedAccount transfer.receiver", "  boundedAccount transfer.sender")]),
    ("R189", "bound", "transfer: metadata unbounded", SR,
     [("    && boundedText transfer.instrumentId.id && boundedMeta transfer.meta", "    && boundedText transfer.instrumentId.id")]),
    ("R190", "bound", "transfer: inputs unbounded", SR,
     [("    && length transfer.inputHoldingCids <= maxInputs\n", "\n")]),

    # Token standard functions (TokenStandard.daml).
    ("T001", "authority", "actors: a superset of a group accepted", TS,
     [("any (\\group -> Set.fromList actors == Set.fromList group) allowed",
       "any (\\group -> Set.fromList group `Set.isSubsetOf` Set.fromList actors) allowed")]),
    ("T002", "authority", "actors: a subset of a group accepted", TS,
     [("any (\\group -> Set.fromList actors == Set.fromList group) allowed",
       "any (\\group -> Set.fromList actors `Set.isSubsetOf` Set.fromList group) allowed")]),
    ("T003", "guard", "iteration arguments: extra leg sides accepted", TS,
     [("require registryIteratedSettlement (null extraTransferLegSides && isNone nextIterationFunding)",
       "require registryIteratedSettlement (isNone nextIterationFunding)")]),
    ("T004", "guard", "iteration arguments: next-iteration funding accepted", TS,
     [("require registryIteratedSettlement (null extraTransferLegSides && isNone nextIterationFunding)",
       "require registryIteratedSettlement (null extraTransferLegSides)")]),
    ("T005", "guard", "iteration arguments: funding amounts not checked", TS,
     [("    forA_ (TextMap.toList fundings) $ \\(_, amount) -> require registryInvalidAmount (amount > 0.0)",
       "    forA_ (TextMap.toList fundings) $ \\(_, _) -> pure ()")]),
    ("T006", "guard", "iteration arguments: extra leg amounts not checked", TS,
     [("  forA_ extraTransferLegSides $ \\leg -> require registryInvalidAmount (leg.amount > 0.0)\n", "")]),
    ("T007", "guard", "withdraw: committed allocation without a deadline allowed", TS,
     [("    None -> raise registryCommittedAllocation", "    None -> pure ()")]),
    ("T008", "boundary", "withdraw: committed allocation withdrawn at the deadline", TS,
     [GT_IMPORT, ("      passed <- isLedgerTimeGT deadline", "      passed <- isLedgerTimeGE deadline")]),
    ("T009", "guard", "withdraw: committed allocation not checked", TS,
     [("  if not allocation.committed then pure () else case", "  if True then pure () else case")]),
    ("T010", "guard", "settle batch: empty legs accepted", TS,
     [("  require registryNoTransferLegs (not (null arg.transferLegs))\n", "")]),
    ("T011", "guard", "settle batch: duplicate leg identifiers accepted", TS,
     [("  require registryDuplicateLeg (unique (map (.transferLegId) arg.transferLegs))\n", "")]),
    ("T012", "guard", "settle batch: leg amounts not checked", TS,
     [("  forA_ arg.transferLegs $ \\leg -> require registryInvalidAmount (leg.amount > 0.0)\n", "")]),
    ("T013", "guard", "settle batch: settlement not checked", TS,
     [("    require registrySettlementMismatch (allocationView.settlement == arg.settlement)\n", "")]),
    ("T014", "guard", "settle batch: allocation admin not checked", TS,
     [("    require registryWrongAdmin (spec.admin == admin)\n", "")]),
    ("T015", "guard", "settle batch: iteration arguments not checked", TS,
     [("    validateNextIterationArgs (isSome spec.nextIterationFunding)\n      finalized.extraTransferLegSides finalized.nextIterationFunding\n", "")]),
    ("T016", "guard", "settle batch: duplicate allocated sides accepted", TS,
     [("  require registryDuplicateLeg\n    (unique [ (authorizer, leg.transferLegId, leg.side) | (authorizer, leg) <- allocated ])\n", "")]),
    ("T017", "guard", "settle batch: missing authorization accepted", TS,
     [("  require registryMissingAuthorization (Set.null (required `Set.difference` allocatedSet))\n", "")]),
    ("T018", "guard", "settle batch: superfluous authorization accepted", TS,
     [("  require registrySuperfluousAuthorization (Set.null (allocatedSet `Set.difference` required))\n", "")]),
    ("T020", "authority", "settle batch: actors not checked", TS,
     [("  checkActors arg.actors [arg.settlement.executors]\n  allocations <-", "  allocations <-")]),
    ("T021", "ordering", "settle batch: results in reverse order", TS,
     [("    allocationSettleResults = results\n", "    allocationSettleResults = reverse results\n")]),
    ("T022", "authority", "settle batch: each settle without the admin", TS,
     [("      actors = allocationView.allocation.admin :: allocationView.settlement.executors",
       "      actors = allocationView.settlement.executors")]),
    ("T023", "authority", "withdraw: actors not checked", TS,
     [("  checkActors actors (accountGroups spec.admin spec.authorizer)\n", "")]),
    ("T024", "guard", "withdraw: committed allocation rule not applied", TS,
     [("  ensureWithdrawIsAllowed spec\n", "")]),
    ("T025", "authority", "cancel: actors not checked", TS,
     [("  checkActors actors [allocationView.settlement.executors]\n", "")]),
    ("T026", "authority", "account groups: the provider alone may not act", TS,
     [("  [principal, provider] -> [[principal], [provider], [principal, provider]]",
       "  [principal, provider] -> [[principal], [principal, provider]]")]),
    ("T027", "authority", "account parties: the provider left out", TS,
     [("    Some provider | provider /= principal -> [principal, provider]", "    Some _ -> [principal]")]),
    ("T028", "guard", "net credit: mint sender side counted", TS,
     [("        | authorizer == mintAccount -> 0.0", "        | False -> 0.0")]),
    ("T029", "guard", "net credit: burn receiver side counted", TS,
     [("        | authorizer == burnAccount -> 0.0", "        | False -> 0.0")]),
    ("T030", "guard", "net credit: sends counted positive", TS,
     [("        | otherwise -> negate leg.amount", "        | otherwise -> leg.amount")]),
    ("T031", "guard", "events: special accounts logged", TS,
     [(" || isNone arg.account.owner)", ")")]),
    ("T032", "guard", "events: empty changes logged", TS,
     [("  not ((null arg.transferLegSides && null arg.inputHoldingCids && null arg.outputHoldingCids) || isNone arg.account.owner)",
       "  not (isNone arg.account.owner)")]),
    ("T033", "guard", "events: nothing logged", TS,
     [("logHoldingsChange emit arg = if holdingsChangeIsLogged arg then emit arg else pure ()",
       "logHoldingsChange _ _ = pure ()")]),
    ("T034", "guard", "events: observers without the provider", TS,
     [("  observers = accountParties allocation.admin allocation.authorizer",
       "  observers = [accountPrincipal allocation.admin allocation.authorizer]")]),
    ("T035", "guard", "events: leg sides swapped", TS,
     [("    SenderSide -> Events.SenderSide\n    ReceiverSide -> Events.ReceiverSide",
       "    SenderSide -> Events.ReceiverSide\n    ReceiverSide -> Events.SenderSide")]),
    ("T036", "guard", "legs: sender side names the sender as other side", TS,
     [("  side = SenderSide\n  otherside = leg.receiver", "  side = SenderSide\n  otherside = leg.sender")]),
    ("T037", "guard", "legs: receiver side names the receiver as other side", TS,
     [("  side = ReceiverSide\n  otherside = leg.sender", "  side = ReceiverSide\n  otherside = leg.receiver")]),
    ("T038", "guard", "legs: authorizers swapped", TS,
     [("[(leg.sender, senderSide leg), (leg.receiver, receiverSide leg)]",
       "[(leg.receiver, senderSide leg), (leg.sender, receiverSide leg)]")]),
    # Conversion functions (docs/MATH.md, section 7).
    ('C001', 'rounding', 'convertToShares rounds up', CP,
     [('convertToShares v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'convertToShares v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Ceil assets t.shares t.assets')]),
    ('C002', 'rounding', 'convertToAssets rounds up', CP,
     [('convertToAssets v shares =\n  let t = checkedTerms v\n  in mulDiv Floor shares t.assets t.shares', 'convertToAssets v shares =\n  let t = checkedTerms v\n  in mulDiv Ceil shares t.assets t.shares')]),
    ('C003', 'rounding', 'previewDeposit rounds up', CP,
     [('previewDeposit v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'previewDeposit v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Ceil assets t.shares t.assets')]),
    ('C004', 'rounding', 'previewMint rounds down', CP,
     [('previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares', 'previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Floor shares t.assets t.shares')]),
    ('C005', 'rounding', 'previewWithdraw rounds down', CP,
     [('previewWithdraw v assets =\n  let t = checkedTerms v\n  in mulDiv Ceil assets t.shares t.assets', 'previewWithdraw v assets =\n  let t = checkedTerms v\n  in mulDiv Floor assets t.shares t.assets')]),
    ('C006', 'rounding', 'previewRedeem rounds up', CP,
     [('previewRedeem v shares =\n  let t = checkedTerms v\n  in mulDiv Floor shares t.assets t.shares', 'previewRedeem v shares =\n  let t = checkedTerms v\n  in mulDiv Ceil shares t.assets t.shares')]),
    ('C007', 'operands', 'convertToShares inverts the price', CP,
     [('convertToShares v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'convertToShares v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.assets t.shares')]),
    ('C008', 'operands', 'convertToAssets inverts the price', CP,
     [('convertToAssets v shares =\n  let t = checkedTerms v\n  in mulDiv Floor shares t.assets t.shares', 'convertToAssets v shares =\n  let t = checkedTerms v\n  in mulDiv Floor shares t.shares t.assets')]),
    ('C009', 'operands', 'previewDeposit inverts the price', CP,
     [('previewDeposit v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'previewDeposit v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.assets t.shares')]),
    ('C010', 'operands', 'previewMint inverts the price', CP,
     [('previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares', 'previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.shares t.assets')]),
    ('C011', 'operands', 'previewWithdraw inverts the price', CP,
     [('previewWithdraw v assets =\n  let t = checkedTerms v\n  in mulDiv Ceil assets t.shares t.assets', 'previewWithdraw v assets =\n  let t = checkedTerms v\n  in mulDiv Ceil assets t.assets t.shares')]),
    ('C012', 'operands', 'previewRedeem inverts the price', CP,
     [('previewRedeem v shares =\n  let t = checkedTerms v\n  in mulDiv Floor shares t.assets t.shares', 'previewRedeem v shares =\n  let t = checkedTerms v\n  in mulDiv Floor shares t.shares t.assets')]),
    ('C013', 'view', 'convertToShares skips the view checks', CP,
     [('convertToShares v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'convertToShares v assets =\n  let t = Terms with assets = v.totalAssets + unit; shares = v.totalShares + virtualShares v.decimalsOffset; room = assetCap v.decimalsOffset - unit - v.totalAssets\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets')]),
    ('C014', 'view', 'convertToAssets skips the view checks', CP,
     [('convertToAssets v shares =\n  let t = checkedTerms v\n  in mulDiv Floor shares t.assets t.shares', 'convertToAssets v shares =\n  let t = Terms with assets = v.totalAssets + unit; shares = v.totalShares + virtualShares v.decimalsOffset; room = assetCap v.decimalsOffset - unit - v.totalAssets\n  in mulDiv Floor shares t.assets t.shares')]),
    ('C015', 'view', 'previewDeposit skips the view checks', CP,
     [('previewDeposit v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'previewDeposit v assets =\n  let t = Terms with assets = v.totalAssets + unit; shares = v.totalShares + virtualShares v.decimalsOffset; room = assetCap v.decimalsOffset - unit - v.totalAssets\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets')]),
    ('C016', 'view', 'previewMint skips the view checks', CP,
     [('previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares', 'previewMint v shares =\n  let t = Terms with assets = v.totalAssets + unit; shares = v.totalShares + virtualShares v.decimalsOffset; room = assetCap v.decimalsOffset - unit - v.totalAssets\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares')]),
    ('C017', 'view', 'previewWithdraw skips the view checks', CP,
     [('previewWithdraw v assets =\n  let t = checkedTerms v\n  in mulDiv Ceil assets t.shares t.assets', 'previewWithdraw v assets =\n  let t = Terms with assets = v.totalAssets + unit; shares = v.totalShares + virtualShares v.decimalsOffset; room = assetCap v.decimalsOffset - unit - v.totalAssets\n  in mulDiv Ceil assets t.shares t.assets')]),
    ('C018', 'view', 'previewRedeem skips the view checks', CP,
     [('previewRedeem v shares =\n  let t = checkedTerms v\n  in mulDiv Floor shares t.assets t.shares', 'previewRedeem v shares =\n  let t = Terms with assets = v.totalAssets + unit; shares = v.totalShares + virtualShares v.decimalsOffset; room = assetCap v.decimalsOffset - unit - v.totalAssets\n  in mulDiv Floor shares t.assets t.shares')]),
    ('C019', 'virtual terms', 'no virtual assets: A + VA becomes A', CI,
     [('      assets = v.totalAssets + unit\n', '      assets = v.totalAssets\n')]),
    ('C020', 'virtual terms', 'no virtual shares: S + VS becomes S', CI,
     [('      shares = v.totalShares + vs\n', '      shares = v.totalShares\n')]),
    ('C021', 'virtual terms', 'virtual assets doubled', CI,
     [('      assets = v.totalAssets + unit\n', '      assets = v.totalAssets + unit + unit\n')]),
    ('C022', 'virtual terms', 'virtual shares without the offset', CI,
     [('      shares = v.totalShares + vs\n', '      shares = v.totalShares + unit\n')]),
    ('C023', 'virtual terms', 'one unit read as 10^-9', CI,
     [('unit = 0.0000000001\n', 'unit = 0.000000001\n')]),
    ('C024', 'offset', 'virtual shares one power of ten too high', CI,
     [('unit [1 .. k]', 'unit [0 .. k]')]),
    ('C025', 'offset', 'virtual shares one power of ten too low', CI,
     [('unit [1 .. k]', 'unit [2 .. k]')]),
    ('C026', 'offset', 'asset bound of the next offset', CI,
     [('assetCap k = mulDiv Floor dmax unit (virtualShares k)', 'assetCap k = mulDiv Floor dmax unit (virtualShares (k + 1))')]),
    ('C027', 'bound', 'KMAX 11', CI,
     [('kmax = 10\n', 'kmax = 11\n')]),
    ('C028', 'bound', 'KMAX 9', CI,
     [('kmax = 10\n', 'kmax = 9\n')]),
    ('C029', 'bound', 'negative offsets accepted', CI,
     [('  | v.decimalsOffset < 0 || v.decimalsOffset > kmax = capacityExceeded', '  | v.decimalsOffset > kmax = capacityExceeded')]),
    ('C030', 'bound', 'offsets above KMAX accepted', CI,
     [('  | v.decimalsOffset < 0 || v.decimalsOffset > kmax = capacityExceeded', '  | v.decimalsOffset < 0 = capacityExceeded')]),
    ('C031', 'bound', 'offset KMAX rejected', CI,
     [('v.decimalsOffset > kmax = capacityExceeded', 'v.decimalsOffset >= kmax = capacityExceeded')]),
    ('C032', 'bound', 'negative assets accepted', CI,
     [('  | v.totalAssets < 0.0 || v.totalShares < 0.0 = capacityExceeded', '  | v.totalShares < 0.0 = capacityExceeded')]),
    ('C033', 'bound', 'negative shares accepted', CI,
     [('  | v.totalAssets < 0.0 || v.totalShares < 0.0 = capacityExceeded', '  | v.totalAssets < 0.0 = capacityExceeded')]),
    ('C034', 'bound', 'asset bound not checked', CI,
     [('  | v.totalAssets > cap - unit = capacityExceeded\n', '')]),
    ('C035', 'bound', 'asset bound one unit tighter', CI,
     [('  | v.totalAssets > cap - unit = capacityExceeded', '  | v.totalAssets >= cap - unit = capacityExceeded')]),
    ('C036', 'bound', 'invariant not checked', CI,
     [('  | v.totalShares > mulDiv Floor (v.totalAssets + unit) vs unit - vs = capacityExceeded\n', '')]),
    ('C037', 'bound', 'invariant one unit tighter', CI,
     [('  | v.totalShares > mulDiv Floor (v.totalAssets + unit) vs unit - vs = capacityExceeded', '  | v.totalShares >= mulDiv Floor (v.totalAssets + unit) vs unit - vs = capacityExceeded')]),
    ('C038', 'bound', 'invariant replaced by the share bound', CI,
     [('  | v.totalShares > mulDiv Floor (v.totalAssets + unit) vs unit - vs = capacityExceeded', '  | v.totalShares > mulDiv Floor cap vs unit - vs = capacityExceeded')]),
    ('C039', 'bound', 'deposit room without the virtual assets', CI,
     [('      room = cap - unit - v.totalAssets\n', '      room = cap - v.totalAssets\n')]),
    ('C040', 'bound', 'convertToShares room not checked', CP,
     [('convertToShares v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'convertToShares v assets =\n  let t = checkedTerms v\n  in mulDiv Floor assets t.shares t.assets')]),
    ('C041', 'bound', 'convertToShares room one unit tighter', CP,
     [('convertToShares v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'convertToShares v assets =\n  let t = checkedTerms v\n  in if assets >= t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets')]),
    ('C042', 'bound', 'previewDeposit room not checked', CP,
     [('previewDeposit v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'previewDeposit v assets =\n  let t = checkedTerms v\n  in mulDiv Floor assets t.shares t.assets')]),
    ('C043', 'bound', 'previewDeposit room one unit tighter', CP,
     [('previewDeposit v assets =\n  let t = checkedTerms v\n  in if assets > t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets', 'previewDeposit v assets =\n  let t = checkedTerms v\n  in if assets >= t.room then capacityExceeded else mulDiv Floor assets t.shares t.assets')]),
    ('C044', 'bound', 'previewMint room not checked', CP,
     [('previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares', 'previewMint v shares =\n  let t = checkedTerms v\n  in mulDiv Ceil shares t.assets t.shares')]),
    ('C045', 'bound', 'previewMint room one unit tighter', CP,
     [('previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares', 'previewMint v shares =\n  let t = checkedTerms v\n  in if shares >= mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares')]),
    ('C046', 'bound', 'previewMint compares shares with the asset room', CP,
     [('previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares', 'previewMint v shares =\n  let t = checkedTerms v\n  in if shares > t.room then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares')]),
    ('C047', 'bound', 'previewMint room rounded up', CP,
     [('previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Floor t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares', 'previewMint v shares =\n  let t = checkedTerms v\n  in if shares > mulDiv Ceil t.room t.shares t.assets then capacityExceeded\n     else mulDiv Ceil shares t.assets t.shares')]),
    ('C048', 'failure', 'capacity identifier changed', FA,
     [('"vault-capacity-exceeded"', '"vault-capacity"')]),
    ('C049', 'bound', 'DMAX one unit lower', CI,
     [('dmax = 9999999999999999999999999999.9999999999\n', 'dmax = 9999999999999999999999999999.9999999998\n')]),

    # The vault (guards, check order, bounds, mode and executor,
    # delegation, conversion call sites; mutants V).
    # Executor and mode (SPEC §5.3 step 1).
    ("V001", "executor", "Permissioned: a non-operator executor accepted", VV,
     [("  when (executor /= v.operator && v.mode == Permissioned) $ raise vaultUnauthorizedExecutor\n", "  pure ()\n")]),
    ("V002", "mode", "the Permissioned rule applied in Permissionless mode", VV,
     [("v.mode == Permissioned) $ raise vaultUnauthorizedExecutor", "v.mode == Permissionless) $ raise vaultUnauthorizedExecutor")]),
    ("V003", "executor", "Permissionless: another requester's request accepted", VV,
     [("  when (executor /= v.operator && any (\\e -> e.requester /= executor) entries) $ raise vaultUnauthorizedExecutor\n", "")]),
    ("V004", "executor", "Permissionless: one own request admits the batch", VV,
     [("any (\\e -> e.requester /= executor) entries", "all (\\e -> e.requester /= executor) entries")]),
    ("V005", "executor", "Permissionless: the operator may not execute", VV,
     [("  when (executor /= v.operator && any (\\e -> e.requester /= executor) entries)", "  when (any (\\e -> e.requester /= executor) entries)")]),
    ("V006", "order", "deposits: requests read before the executor check", VV,
     [("        executorBeforeRead this executor\n        batchBeforeRead Deposit this executor (map (\\i -> coerceContractId i.request) items)\n        requests <- forA items (\\i -> fetch i.request)\n        let entries = zipWith (depositEntry",
       "        batchBeforeRead Deposit this executor (map (\\i -> coerceContractId i.request) items)\n        requests <- forA items (\\i -> fetch i.request)\n        executorBeforeRead this executor\n        let entries = zipWith (depositEntry")]),
    ("V007", "order", "redemptions: requests read before the executor check", VV,
     [("        executorBeforeRead this executor\n        batchBeforeRead Redeem this executor (map (\\i -> coerceContractId i.request) items)\n        requests <- forA items (\\i -> fetch i.request)\n        let entries = zipWith (redeemEntry",
       "        batchBeforeRead Redeem this executor (map (\\i -> coerceContractId i.request) items)\n        requests <- forA items (\\i -> fetch i.request)\n        executorBeforeRead this executor\n        let entries = zipWith (redeemEntry")]),
    # Pause (step 2, SPEC §5.5, §5.6; D-14).
    ("V010", "guard", "deposits execute while paused", VV,
     [("  when (kind == Deposit && v.paused) $ raise vaultPaused\n", "")]),
    ("V011", "guard", "redemptions refused while paused", VV,
     [("  when (kind == Deposit && v.paused) $ raise vaultPaused\n", "  when v.paused $ raise vaultPaused\n")]),
    ("V012", "guard", "asset additions execute while paused", VV,
     [("        when paused $ raise vaultPaused\n", "")]),
    ("V013", "guard", "pausing a paused vault accepted", VV,
     [("        when paused $ raise vaultAlreadyPaused\n", "")]),
    ("V014", "guard", "unpausing an active vault accepted", VV,
     [("        unless paused $ raise vaultNotPaused\n", "")]),
    ("V015", "state", "pause leaves the flag unset", VV,
     [("        create this with paused = True\n", "        create this\n")]),
    ("V016", "state", "unpause leaves the flag set", VV,
     [("        create this with paused = False\n", "        create this\n")]),
    # Batch (steps 3, 4).
    ("V020", "bound", "batch of 25 refused", VV,
     [("length requestCids <= maxBatchSize", "length requestCids < maxBatchSize")]),
    ("V021", "bound", "empty batch accepted", VV,
     [("unless (not (null requestCids) && length requestCids <= maxBatchSize)", "unless (length requestCids <= maxBatchSize)")]),
    ("V022", "bound", "batch cap 26", IV,
     [("maxBatchSize = 25\n", "maxBatchSize = 26\n")]),
    ("V023", "guard", "duplicate request accepted", VV,
     [("  unless (unique requestCids) $ raise vaultDuplicateRequest\n", "")]),
    # Check order of the batch (steps 1 to 4).
    ("V024", "order", "step 2 before step 1", VV,
     [("  when (executor /= v.operator && any (\\e -> e.requester /= executor) entries) $ raise vaultUnauthorizedExecutor\n  -- Steps 2 to 4.\n  batchChecks kind v (map (.requestCid) entries)\n",
       "  batchChecks kind v (map (.requestCid) entries)\n  when (executor /= v.operator && any (\\e -> e.requester /= executor) entries) $ raise vaultUnauthorizedExecutor\n")]),
    ("V025", "order", "step 3 before step 2", VV,
     [("  when (kind == Deposit && v.paused) $ raise vaultPaused\n  -- Step 3: 1 to 25 requests.\n  unless (not (null requestCids) && length requestCids <= maxBatchSize) $ raise vaultBatchSize\n",
       "  unless (not (null requestCids) && length requestCids <= maxBatchSize) $ raise vaultBatchSize\n  when (kind == Deposit && v.paused) $ raise vaultPaused\n")]),
    ("V026", "order", "step 4 before step 3", VV,
     [("  unless (not (null requestCids) && length requestCids <= maxBatchSize) $ raise vaultBatchSize\n  -- Step 4: no request twice.\n  unless (unique requestCids) $ raise vaultDuplicateRequest\n",
       "  unless (unique requestCids) $ raise vaultDuplicateRequest\n  unless (not (null requestCids) && length requestCids <= maxBatchSize) $ raise vaultBatchSize\n")]),
    ("V027", "order", "step 4 after the request checks", VV,
     [("  unless (unique requestCids) $ raise vaultDuplicateRequest\n", ""),
      ("  let planned = reverse plannedRev\n", "  let planned = reverse plannedRev\n  unless (unique (map (.requestCid) entries)) $ raise vaultDuplicateRequest\n")]),
    # Request checks (steps 5 to 12) and their order.
    ("V030", "guard", "request of another vault accepted by the vault", VV,
     [("  unless (e.operator == v.operator && e.vaultId == v.vaultId) $ raise vaultWrongVault\n  -- Step 6", "  -- Step 6")]),
    ("V031", "guard", "request's vault identifier not checked by the vault", VV,
     [("  unless (e.operator == v.operator && e.vaultId == v.vaultId) $ raise vaultWrongVault\n  -- Step 6", "  unless (e.operator == v.operator) $ raise vaultWrongVault\n  -- Step 6")]),
    ("V032", "guard", "deadline not checked by the vault", VV,
     [("  open <- isLedgerTimeLT e.deadline\n  unless open $ raise vaultRequestExpired\n", "")]),
    ("V033", "boundary", "vault accepts a request at its deadline", VV,
     [LT_IMPORT, ("  open <- isLedgerTimeLT e.deadline\n", "  open <- isLedgerTimeLE e.deadline\n")]),
    ("V034", "order", "step 6 before step 5", VV,
     [("  unless (e.operator == v.operator && e.vaultId == v.vaultId) $ raise vaultWrongVault\n  -- Step 6: before the deadline, the predicate of the settlement's own deadline check.\n  open <- isLedgerTimeLT e.deadline\n  unless open $ raise vaultRequestExpired\n",
       "  open <- isLedgerTimeLT e.deadline\n  unless open $ raise vaultRequestExpired\n  unless (e.operator == v.operator && e.vaultId == v.vaultId) $ raise vaultWrongVault\n")]),
    ("V035", "guard", "funding allocation's view not checked", VV,
     [("      unless (fundingMatches (view allocation) settlement inputAdmin e.payAccount input e.deadline) $\n        raise vaultAllocationMismatch\n",
       "      unless (fundingMatches (view allocation) settlement inputAdmin e.payAccount input e.deadline || True) $\n        raise vaultAllocationMismatch\n")]),
    ("V036", "guard", "funding presence not checked by the vault", VV,
     [("    (False, None) -> pure ()\n    _ -> raise vaultAllocationMismatch\n  let k", "    _ -> pure ()\n  let k")]),
    ("V037", "order", "step 7 before step 6", VV,
     [("  open <- isLedgerTimeLT e.deadline\n  unless open $ raise vaultRequestExpired\n  -- Step 7",
       "  -- Step 7"),
      ("    (False, None) -> pure ()\n    _ -> raise vaultAllocationMismatch\n  let k",
       "    (False, None) -> pure ()\n    _ -> raise vaultAllocationMismatch\n  open <- isLedgerTimeLT e.deadline\n  unless open $ raise vaultRequestExpired\n  let k")]),
    ("V038", "guard", "funding: settlement not compared", IV,
     [("  v.settlement == settlement\n    && v.allocation.admin == admin\n    && v.allocation.authorizer == payAccount", "  v.allocation.admin == admin\n    && v.allocation.authorizer == payAccount")]),
    ("V039", "guard", "funding: admin not compared", IV,
     [("  v.settlement == settlement\n    && v.allocation.admin == admin\n    && v.allocation.authorizer == payAccount", "  v.settlement == settlement\n    && v.allocation.authorizer == payAccount")]),
    ("V040", "guard", "funding: authorizer not compared", IV,
     [("    && v.allocation.authorizer == payAccount\n    && v.allocation.transferLegSides == [senderSide leg]\n    && v.allocation.settlementDeadline", "    && v.allocation.transferLegSides == [senderSide leg]\n    && v.allocation.settlementDeadline")]),
    ("V041", "guard", "funding: leg sides not compared", IV,
     [("    && v.allocation.transferLegSides == [senderSide leg]\n    && v.allocation.settlementDeadline == Some deadline\n", "    && v.allocation.settlementDeadline == Some deadline\n")]),
    ("V042", "guard", "funding: deadline not compared", IV,
     [("    && v.allocation.settlementDeadline == Some deadline\n", "")]),
    ("V043", "guard", "funding: next-iteration funding not checked", IV,
     [("    && v.allocation.settlementDeadline == Some deadline\n    && isNone v.allocation.nextIterationFunding\n", "    && v.allocation.settlementDeadline == Some deadline\n")]),
    ("V044", "guard", "funding template not compared (T-06)", VV,
     [("    same <- sameTemplate funding vaultIn\n    unless same $ raise vaultAllocationMismatch\n  (vaultOut, change')", "    same <- sameTemplate funding vaultIn\n    unless (same || True) $ raise vaultAllocationMismatch\n  (vaultOut, change')")]),
    ("V045", "guard", "template comparison always succeeds (T-06)", IV,
     [("  pure (interfaceTypeRep x == interfaceTypeRep y)\n", "  pure True\n")]),
    ("V047", "guard", "prepare: a delegated funding allocation refused", VV,
     [("    (Some f, None) -> pure f\n    (None, Some f) -> pure f\n", "    (Some f, None) -> raise vaultAllocationMismatch\n    (None, Some f) -> pure f\n")]),
    ("V048", "guard", "prepare: a requester's funding allocation refused", VV,
     [("    (Some f, None) -> pure f\n    (None, Some f) -> pure f\n", "    (Some f, None) -> pure f\n    (None, Some f) -> raise vaultAllocationMismatch\n")]),
    ("V049", "guard", "redemption: the previous redemption's change not spent", VV,
     [("(e.vaultInputs ++ change) outContext v.operator", "e.vaultInputs outContext v.operator")]),
    ("V050", "bound", "deposit asset bound one unit tighter", VV,
     [("      unless (e.amount <= assetCap k - unit - a) $ raise vaultCapacityExceeded\n", "      unless (e.amount < assetCap k - unit - a) $ raise vaultCapacityExceeded\n")]),
    ("V051", "conversion", "deposit priced on the state before the batch", VV,
     [("      let shares = previewDeposit (runningView v a s) e.amount\n", "      let shares = previewDeposit (runningView v v.totalAssets v.totalShares) e.amount\n")]),
    ("V052", "guard", "deposit of zero shares accepted by the vault", VV,
     [("      unless (shares > 0.0) $ raise vaultZeroShares\n", "")]),
    ("V053", "guard", "deposit slippage not checked by the vault", VV,
     [("      unless (shares >= e.minOut) $ raise vaultSlippage\n", "")]),
    ("V054", "boundary", "deposit output equal to minOut refused", VV,
     [("      unless (shares >= e.minOut) $ raise vaultSlippage\n", "      unless (shares > e.minOut) $ raise vaultSlippage\n")]),
    ("V055", "order", "deposit step 11 before step 10", VV,
     [("      unless (shares > 0.0) $ raise vaultZeroShares\n      unless (shares >= e.minOut) $ raise vaultSlippage\n",
       "      unless (shares >= e.minOut) $ raise vaultSlippage\n      unless (shares > 0.0) $ raise vaultZeroShares\n")]),
    ("V056", "state", "deposit leaves S unchanged in the running state", VV,
     [("a + e.amount, s + shares)", "a + e.amount, s)")]),
    ("V057", "state", "deposit leaves A unchanged in the running state", VV,
     [("a + e.amount, s + shares)", "a, s + shares)")]),
    ("V058", "conversion", "deposit output leg for the assets, not the shares", VV,
     [("      let output = outLeg kind v.vaultAccount v.asset v.shareInstrument e.receiver shares\n", "      let output = outLeg kind v.vaultAccount v.asset v.shareInstrument e.receiver e.amount\n")]),
    ("V060", "conversion", "redemption priced on the state before the batch", VV,
     [("      let assets = previewRedeem (runningView v a s) e.amount\n", "      let assets = previewRedeem (runningView v v.totalAssets v.totalShares) e.amount\n")]),
    ("V061", "guard", "redemption of zero assets accepted by the vault", VV,
     [("      unless (assets > 0.0) $ raise vaultZeroAssets\n", "")]),
    ("V062", "guard", "redemption slippage not checked by the vault", VV,
     [("      unless (assets >= e.minOut) $ raise vaultSlippage\n", "")]),
    ("V063", "boundary", "redemption output equal to minOut refused", VV,
     [("      unless (assets >= e.minOut) $ raise vaultSlippage\n", "      unless (assets > e.minOut) $ raise vaultSlippage\n")]),
    ("V126", "guard", "redemption of more than S shares reaches the successor", VV,
     [("      unless (e.amount <= s && assets <= a) $ raise vaultInsufficientAssets\n", "      unless (assets <= a) $ raise vaultInsufficientAssets\n")]),
    ("V065", "boundary", "redemption of exactly A refused", VV,
     [("      unless (e.amount <= s && assets <= a) $ raise vaultInsufficientAssets\n", "      unless (e.amount <= s && assets < a) $ raise vaultInsufficientAssets\n")]),
    ("V066", "order", "redemption step 11 before step 10", VV,
     [("      unless (assets > 0.0) $ raise vaultZeroAssets\n      unless (assets >= e.minOut) $ raise vaultSlippage\n",
       "      unless (assets >= e.minOut) $ raise vaultSlippage\n      unless (assets > 0.0) $ raise vaultZeroAssets\n")]),
    ("V067", "order", "redemption step 12 before step 11", VV,
     [("      unless (assets >= e.minOut) $ raise vaultSlippage\n      -- More shares than `S` exist only outside the vault (T-13); refuse them\n      -- here rather than at the successor's `ensure` (`test_vault_insufficientAssets_amountAboveSupply`).\n      unless (e.amount <= s && assets <= a) $ raise vaultInsufficientAssets\n",
       "      -- More shares than `S` exist only outside the vault (T-13); refuse them\n      -- here rather than at the successor's `ensure` (`test_vault_insufficientAssets_amountAboveSupply`).\n      unless (e.amount <= s && assets <= a) $ raise vaultInsufficientAssets\n      unless (assets >= e.minOut) $ raise vaultSlippage\n")]),
    ("V068", "state", "redemption leaves A unchanged in the running state", VV,
     [("a - assets, s - e.amount)", "a, s - e.amount)")]),
    ("V069", "conversion", "redemption output leg for the shares, not the assets", VV,
     [("      let output = outLeg kind v.vaultAccount v.asset v.shareInstrument e.receiver assets\n", "      let output = outLeg kind v.vaultAccount v.asset v.shareInstrument e.receiver e.amount\n")]),
    # Phases and the successor.
    ("V070", "order", "every request allocated and settled in turn", VV,
     [("  (preparedRev, _) <- foldlA (\\(acc, change) p -> do\n      (q, change') <- prepare kind v assetContext shareContext change p\n      pure (q :: acc, change'))\n    ([], []) planned\n  let prepared = reverse preparedRev\n  -- Every settlement.\n  forA_ prepared (settle kind v assetContext shareContext)\n",
       "  _ <- foldlA (\\change p -> do\n      (q, change') <- prepare kind v assetContext shareContext change p\n      settle kind v assetContext shareContext q\n      pure change') [] planned\n")]),
    ("V071", "order", "each request checked and allocated in turn", VV,
     [("  (plannedRev, a, s) <- foldlA (checkRequest kind v) ([], v.totalAssets, v.totalShares) entries\n  let planned = reverse plannedRev\n  -- Every allocation, created and checked before any settlement (`docs/SPEC.md` §5.3). A\n  -- redemption's vault allocation also spends the change of the previous\n  -- one (`docs/SPEC.md` §5.4).\n  (preparedRev, _) <- foldlA (\\(acc, change) p -> do\n      (q, change') <- prepare kind v assetContext shareContext change p\n      pure (q :: acc, change'))\n    ([], []) planned\n  let prepared = reverse preparedRev\n",
       "  (preparedRev, a, s, _) <- foldlA (\\(acc, a0, s0, change) e -> do\n      (ps, a1, s1) <- checkRequest kind v ([], a0, s0) e\n      (q, change') <- case ps of\n        (x :: _) -> prepare kind v assetContext shareContext change x\n        [] -> abort \"unreachable\"\n      pure (q :: acc, a1, s1, change')) ([], v.totalAssets, v.totalShares, []) entries\n  let prepared = reverse preparedRev\n      planned = map (.planned) prepared\n")]),
    ("V072", "state", "successor keeps the totals before the batch", VV,
     [("  successor <- create v with totalAssets = a; totalShares = s\n", "  successor <- create v\n")]),
    # Asset additions (SPEC §5.5).
    ("V080", "guard", "asset addition of zero accepted", VV,
     [("        unless (amount > 0.0) $ raise vaultInvalidAmount\n", "")]),
    ("V081", "guard", "asset addition with no shares accepted", VV,
     [("        unless (totalShares > 0.0) $ raise vaultNoShares\n", "")]),
    ("V082", "bound", "asset addition bound one unit tighter", VV,
     [("        unless (amount <= assetCap decimalsOffset - unit - totalAssets) $ raise vaultCapacityExceeded\n", "        unless (amount < assetCap decimalsOffset - unit - totalAssets) $ raise vaultCapacityExceeded\n")]),
    ("V083", "guard", "asset addition's allocation view not checked", VV,
     [("        unless (fundingMatchesAdd (view f) settlement asset.admin source leg) $ raise vaultAllocationMismatch\n", "")]),
    ("V084", "guard", "asset addition's allocation template not compared (T-06)", VV,
     [("        same <- sameTemplate funding vaultIn\n        unless same $ raise vaultAllocationMismatch\n        settleAt", "        settleAt")]),
    ("V085", "state", "asset addition leaves A unchanged", VV,
     [("        create this with totalAssets = totalAssets + amount\n", "        create this\n")]),
    ("V086", "order", "asset addition: amount checked before the pause", VV,
     [("        when paused $ raise vaultPaused\n        unless (amount > 0.0) $ raise vaultInvalidAmount\n", "        unless (amount > 0.0) $ raise vaultInvalidAmount\n        when paused $ raise vaultPaused\n")]),
    ("V087", "order", "asset addition: shares checked before the amount", VV,
     [("        unless (amount > 0.0) $ raise vaultInvalidAmount\n        unless (totalShares > 0.0) $ raise vaultNoShares\n", "        unless (totalShares > 0.0) $ raise vaultNoShares\n        unless (amount > 0.0) $ raise vaultInvalidAmount\n")]),
    ("V088", "order", "asset addition: capacity checked before the shares", VV,
     [("        unless (totalShares > 0.0) $ raise vaultNoShares\n        unless (amount <= assetCap decimalsOffset - unit - totalAssets) $ raise vaultCapacityExceeded\n", "        unless (amount <= assetCap decimalsOffset - unit - totalAssets) $ raise vaultCapacityExceeded\n        unless (totalShares > 0.0) $ raise vaultNoShares\n")]),
    ("V089", "order", "asset addition: allocation checked before the capacity", VV,
     [("        unless (amount <= assetCap decimalsOffset - unit - totalAssets) $ raise vaultCapacityExceeded\n        -- A leg from the vault account to itself brings nothing into custody.\n        when (source == vaultAccount) $ raise vaultAllocationMismatch\n        let settlement = addAssetsSettlement operator vaultId (coerceContractId self)\n            leg = addAssetsLeg vaultAccount asset source amount\n        f <- fetch funding\n        unless (fundingMatchesAdd (view f) settlement asset.admin source leg) $ raise vaultAllocationMismatch\n",
       "        -- A leg from the vault account to itself brings nothing into custody.\n        when (source == vaultAccount) $ raise vaultAllocationMismatch\n        let settlement = addAssetsSettlement operator vaultId (coerceContractId self)\n            leg = addAssetsLeg vaultAccount asset source amount\n        f <- fetch funding\n        unless (fundingMatchesAdd (view f) settlement asset.admin source leg) $ raise vaultAllocationMismatch\n        unless (amount <= assetCap decimalsOffset - unit - totalAssets) $ raise vaultCapacityExceeded\n")]),
    # Delegation (SPEC §4.2) and cancellation.
    ("V090", "delegation", "delegation: vault not checked", VV,
     [("  unless (v.operator == operator && v.vaultId == vaultId) $ raise vaultWrongVault\n", "")]),
    ("V091", "delegation", "delegation: deadline not checked", VV,
     [("  open <- isLedgerTimeLT deadline\n  unless open $ raise vaultRequestExpired\n", "")]),
    ("V092", "delegation", "delegation: allowed at the deadline", VV,
     [LT_IMPORT, ("  open <- isLedgerTimeLT deadline\n", "  open <- isLedgerTimeLE deadline\n")]),
    ("V093", "delegation", "delegation: output leg not checked", VV,
     [("  unless (receiptLeg == expected) $ raise vaultAllocationMismatch\n", "")]),
    ("V094", "delegation", "delegation: slippage not checked", VV,
     [("  unless (receiptLeg.amount > 0.0 && receiptLeg.amount >= minOut) $ raise vaultSlippage\n", "")]),
    ("V095", "delegation", "delegation: a zero output accepted", VV,
     [("receiptLeg.amount > 0.0 && receiptLeg.amount >= minOut", "receiptLeg.amount >= minOut")]),
    ("V096", "delegation", "delegation: output equal to minOut refused", VV,
     [("receiptLeg.amount > 0.0 && receiptLeg.amount >= minOut", "receiptLeg.amount > 0.0 && receiptLeg.amount > minOut")]),
    ("V097", "delegation", "delegation: funding allocated for a funded request", VV,
     [("  funding <- if funded then pure None else do\n", "  funding <- if False then pure None else do\n")]),
    ("V098", "delegation", "delegation: receipt allocation without the deadline", VV,
     [("(receiverSide receiptLeg) (Some deadline) False)", "(receiverSide receiptLeg) None False)")]),
    ("V099", "delegation", "delegation: funding allocation committed", VV,
     [("(senderSide input) (Some deadline) False)", "(senderSide input) (Some deadline) True)")]),
    ("V100", "guard", "cancellation: another request's allocation withdrawn", VV,
     [("    unless ((view allocation).settlement == settlement) $ raise vaultAllocationMismatch\n", "")]),
    ("V101", "archival", "cancellation: allocations not withdrawn", VV,
     [("    exercise cid Allocation_Withdraw with actors = [requester]; extraArgs\n", "    pure ()\n")]),
    # Ensure clauses (SPEC §4.1, §4.2; T-14).
    ("V110", "bound", "request of a zero amount accepted", IV,
     [("  | amount > 0.0 && minOut >= 0.0 = True\n", "  | amount >= 0.0 && minOut >= 0.0 = True\n")]),
    ("V111", "bound", "request with a negative minOut accepted", IV,
     [("  | amount > 0.0 && minOut >= 0.0 = True\n", "  | amount > 0.0 = True\n")]),
    ("V112", "bound", "state: A one unit above the asset bound accepted", IV,
     [("  | otherwise = a <= assetCap k - unit && s <= shareCap k - virtualShares k\n", "  | otherwise = a <= assetCap k && s <= shareCap k - virtualShares k\n")]),
    ("V113", "bound", "state: S one unit above the share bound accepted", IV,
     [("  | otherwise = a <= assetCap k - unit && s <= shareCap k - virtualShares k\n", "  | otherwise = a <= assetCap k - unit && s <= shareCap k - virtualShares k + unit\n")]),
    ("V114", "bound", "state: offset 11 accepted", IV,
     [("  | k < 0 || k > kmax = False\n", "  | k < 0 || k > kmax + 1 = False\n")]),
    ("V115", "bound", "state: negative totals accepted", IV,
     [("  | a < 0.0 || s < 0.0 = False\n", "")]),
    ("V116", "bound", "state: empty identifier accepted", VV,
     [("    ensure not (T.isEmpty vaultId) && T.length vaultId <= maxVaultIdLength\n", "    ensure T.length vaultId <= maxVaultIdLength\n")]),
    ("V117", "bound", "state: identifier of 246 characters accepted", VV,
     [("    ensure not (T.isEmpty vaultId) && T.length vaultId <= maxVaultIdLength\n", "    ensure not (T.isEmpty vaultId) && T.length vaultId <= maxVaultIdLength + 1\n")]),
    ("V118", "bound", "state: share instrument of another admin accepted", VV,
     [("      && shareInstrument.admin == operator && vaultAccount.owner == Some operator\n", "      && vaultAccount.owner == Some operator\n")]),
    ("V119", "bound", "state: vault account of another owner accepted", VV,
     [("      && shareInstrument.admin == operator && vaultAccount.owner == Some operator\n", "      && shareInstrument.admin == operator\n")]),
    ("V120", "bound", "state: metadata unbounded", VV,
     [("      && boundedMeta meta\n      && validState decimalsOffset totalAssets totalShares\n", "      && validState decimalsOffset totalAssets totalShares\n")]),
    ("V121", "bound", "deposit request: vault identifier unbounded", VV,
     [("    ensure requestValid amount minOut\n      && T.length vaultId <= maxTextLength && boundedAccountId payAccount && boundedAccountId receiver && boundedMeta meta\n\n    choice DepositRequest_Allocate",
       "    ensure requestValid amount minOut\n      && boundedAccountId payAccount && boundedAccountId receiver && boundedMeta meta\n\n    choice DepositRequest_Allocate")]),
    ("V122", "bound", "redemption request: accounts and metadata unbounded", VV,
     [("    ensure requestValid amount minOut\n      && T.length vaultId <= maxTextLength && boundedAccountId payAccount && boundedAccountId receiver && boundedMeta meta\n\n    choice RedeemRequest_Allocate",
       "    ensure requestValid amount minOut\n      && T.length vaultId <= maxTextLength\n\n    choice RedeemRequest_Allocate")]),
    ("V125", "order", "deposit batch checks only after the requests are read", VV,
     [("        executorBeforeRead this executor\n        batchBeforeRead Deposit this executor (map (\\i -> coerceContractId i.request) items)\n", "        executorBeforeRead this executor\n")]),
    ("V124", "guard", "asset addition from the vault account accepted", VV,
     [("        when (source == vaultAccount) $ raise vaultAllocationMismatch\n", "")]),
    ("V123", "guard", "redemption: the batch passes on the first change only", VV,
     [("      pure (q :: acc, change'))\n", "      pure (q :: acc, change))\n")]),
]


# Mutants left out because no input can tell them from the code, with the
# argument for each. They are printed with every run, so that the record and
# the list stay together; a reviewer checks each argument.
EQUIVALENT = [
    ("V046", f"{VV}, `prepare`, the `case` on `(allocations.funding, e.fundingAllocation)`",
     "Adds the branch `(Some f, Some _) -> pure f`, accepting a funding allocation both from the "
     "delegation and from the item. No execution reaches that branch. Step 7 (`checkRequest`, "
     "phase 1, before any `prepare`) raises `vault-allocation-mismatch` unless the pair "
     "`(e.funded, e.fundingAllocation)` is `(True, Some _)` or `(False, None)`. The delegation "
     "returns `funding = None` exactly when the request's `funded` is true "
     "(`delegateAllocations`: `funding <- if funded then pure None else ...`), and it is exercised "
     "on the same request contract whose `funded` field `e.funded` was read from, which no choice "
     "changes in between: a contract's fields are immutable. So the pair in `prepare` is always "
     "`(None, Some _)` or `(Some _, None)`, both handled by the unchanged branches. Any mutation "
     "of the unreachable catch-all branch is equivalent by the same argument. The reachable "
     "branches at this site are mutants V047 and V048, which tests kill."),
    ("V064", f"{VV}, `checkRequest`, the redemption's step 12, "
     "`unless (e.amount <= s && assets <= a) $ raise vaultInsufficientAssets`",
     "Removes `assets <= a`, keeping `e.amount <= s`. When `amount <= s`, `assets = previewRedeem` "
     "is `amount * (a + VA) / (s + VS)` rounded down, and `amount * (a + VA) / (s + VS) <= "
     "s * (a + VA) / (s + VS) < a + VA`, because `VS > 0`; a value below `a + VA = a + 10^-10` "
     "rounds down to at most `a`, since `a` is a multiple of `10^-10`. So `assets <= a` holds "
     "whenever `amount <= s` does (SPEC 5.4, the K-02 observation; MATH 7, K-02), and no input "
     "can tell the mutant apart. The other mutants at this site are killed: V126 removes "
     "`amount <= s`, V065 makes `assets < a`, V067 moves the check before step 11."),
    ("V127", f"{VV}, `prepare`, `when (isSome e.fundingAllocation)` before the template identity check",
     "Replaces the guard with `when True`, so the vault also compares the template of an unfunded "
     "request's funding allocation with its own allocation `vaultIn`. That "
     "allocation was created in the same execution by the request's delegation choice, through the "
     "factory recorded in `VaultState` at the same registry as `vaultIn` (SPEC 4.2, 5.3), and both "
     "registries in scope create one allocation template for every side: TestTokenV2 "
     "`TokenAllocationV2` (Splice 0.8.4 `TestTokenV2/Allocation.daml`) and the share registry's "
     "`ShareAllocation`. So the comparison always succeeds and no test can tell the mutant apart. "
     "Equivalence holds for registries that use one allocation template per factory; a registry "
     "with a template per side would make the mutant refuse genuine unfunded requests."),
    ("V128", f"{VV}, `checkRequest`, the deposit's step 12, "
     "`unless (shares <= shareCap k - virtualShares k - s) $ raise vaultCapacityExceeded`",
     "Removes the share-bound check. Step 9's `previewDeposit` fails first "
     "unless `s + VS <= 10^k (a + VA)` (MATH 7, step 1), and mints `shares = floor(d (s + VS) / "
     "(a + VA)) <= 10^k d`; so `s + VS + shares <= 10^k (a + d + VA)`, and step 8 gives "
     "`a + d + VA <= AMAX(k)`, hence `s + VS + shares <= 10^k AMAX(k) = shareCap k` (K-06). The "
     "check can never fail, so no input tells the mutant apart; it is kept as defence in depth "
     "(SPEC 5.3, step 12)."),
]


def run(cmd, cwd, sdk, timeout):
    env = dict(os.environ, DPM_SDK_VERSION=sdk)
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr, False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return None, out, True


LOG_DIR = None  # --log-dir: where each mutant's test output is kept


def evaluate(work, sdk, timeout, log_name=None):
    """(outcome, failing tests) for the workspace as it is."""
    code, out, timed_out = run(["dpm", "build", "--enable-multi-package=no"], os.path.join(work, PKG), sdk, timeout)
    if timed_out:
        return "package build exceeded the time limit", []
    if code != 0:
        return "package build failed", []
    code, out, timed_out = run(["dpm", "test"], os.path.join(work, TEST), sdk, timeout)
    if LOG_DIR and log_name:
        with open(os.path.join(LOG_DIR, log_name + ".txt"), "w") as f:
            f.write(out)
    if timed_out:
        return "test run exceeded the time limit", []
    failed = sorted(set(re.findall(r"daml/[^\s:]+\.daml:(test_\w+): failed", out)))
    passed = re.findall(r"daml/[^\s:]+\.daml:(test_\w+): ok", out)
    if failed:
        return "tests failed", failed
    if code != 0:
        return "test build failed", []
    if not passed:
        return "no test ran", []
    return "all tests passed", []


def fresh_workspace():
    work = tempfile.mkdtemp(prefix="mutate-registry-")
    for rel in (PKG, TEST, VENDOR):
        shutil.copytree(os.path.join(ROOT, rel), os.path.join(work, rel),
                        ignore=shutil.ignore_patterns(".daml"))
    for rel in DEP_DARS:
        shutil.copytree(os.path.join(ROOT, rel), os.path.join(work, rel))
    return work


def run_mutant(mutant, sdk, timeout):
    mid, area, desc, path, edits = mutant
    work = fresh_workspace()
    try:
        target = os.path.join(work, path)
        src = open(target).read()
        # The line of the last edit, which is the mutated code (an import
        # edit, when present, comes first).
        line = src[:src.index(edits[-1][0])].count("\n") + 1
        for old, new in edits:
            src = src.replace(old, new, 1)
        open(target, "w").write(src)
        start = time.time()
        outcome, failed = evaluate(work, sdk, timeout, mid)
        return mid, area, desc, path, line, outcome, failed, time.time() - start
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sdk", default="3.4.11")
    p.add_argument("--only", default="")
    p.add_argument("--prefix", default="")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--log-dir", default="")
    p.add_argument("--check-only", action="store_true",
                   help="only check that every mutant applies exactly once (run by scripts/ci.sh)")
    args = p.parse_args()
    global LOG_DIR
    if args.log_dir:
        os.makedirs(args.log_dir, exist_ok=True)
        LOG_DIR = os.path.abspath(args.log_dir)
    only = set(filter(None, args.only.split(",")))
    mutants = [m for m in MUTANTS if (not only or m[0] in only) and m[0].startswith(args.prefix)]

    ids = [m[0] for m in MUTANTS]
    if len(ids) != len(set(ids)):
        print("mutate: duplicate mutant identifiers")
        return 1
    # Every edit of every mutant must apply exactly once to the current sources.
    for mid, _, _, path, edits in mutants:
        text = open(os.path.join(ROOT, path)).read()
        for old, _ in edits:
            count = text.count(old)
            if count != 1:
                print(f"mutate: {mid} matches {count} times in {path}: {old[:60]!r}; fix the mutant")
                return 1
    if args.check_only:
        print(f"mutate: {len(mutants)} mutants apply exactly once; {len(EQUIVALENT)} recorded as equivalent")
        return 0

    work = fresh_workspace()
    try:
        start = time.time()
        outcome, _ = evaluate(work, args.sdk, args.timeout)
        print(f"baseline (SDK {args.sdk}): {outcome} ({time.time() - start:.0f} s)", flush=True)
        if outcome != "all tests passed":
            return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for mid, site, argument in EQUIVALENT:
        print(f"equivalent, not run: {mid} at {site}: {argument}")
    print("| Mutant | Area | Mutation | Location | Result | Killed by |")
    print("|---|---|---|---|---|---|", flush=True)
    survivors = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for mid, area, desc, path, line, outcome, failed, _ in pool.map(
                lambda m: run_mutant(m, args.sdk, args.timeout), mutants):
            killed = outcome != "all tests passed"
            survivors += 0 if killed else 1
            by = ", ".join(f"`{t}`" for t in failed) if failed else outcome
            print(f"| {mid} | {area} | {desc} | `{os.path.basename(path)}:{line}` | "
                  f"{'killed' if killed else 'SURVIVED'} | {by if killed else ''} |", flush=True)
    print(f"mutate: SDK {args.sdk}: {len(mutants)} mutants, {len(mutants) - survivors} killed, "
          f"{survivors} surviving")
    return 0 if survivors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
