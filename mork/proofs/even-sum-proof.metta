;; Auto-generated MORK atoms from event journal

;; Initialize MORK space
!(mm2-exec &mork 1)

!(add-atom &mork (State "even-sum-proof" "s1" "Prove: if n even and m even, then n+m even" "open" "or"))
!(add-atom &mork (Claim "even-sum-proof" "c1" "If n is even, then n = 2k for some integer k" "conjectural"))
!(add-atom &mork (Move "even-sum-proof" "m1" "s1" "open" "reduction" "Expand definition of even numbers"))
!(add-atom &mork (Attempt "even-sum-proof" "a1" "s1" "supported" "llm-explorer-1" "Expanded definition: n=2k, m=2j, so n+m=2(k+j)"))
!(add-atom &mork (Edge "e1" SUPPORTED_BY "s1" "c1"))
!(add-atom &mork (Edge "e2" PROPOSES "s1" "m1"))
!(add-atom &mork (Edge "e3" ON_STATE "a1" "s1"))
!(add-atom &mork (Edge "e4" ON_MOVE "a1" "m1"))


;; ============================================
;; QUERY SECTION: Match patterns for querying proof data
;; ============================================

;; Query 1: Find all open states
!(test (collapse (match &mork (State "even-sum-proof" $sid $desc "open" $kind)
                           (open-state $sid $desc $kind)))
       ((open-state "s1" "Prove: if n even and m even, then n+m even" "or")))

;; Query 2: Find all claims and their status
!(test (collapse (match &mork (Claim "even-sum-proof" $cid $stmt $status)
                          (claim-info $cid $stmt $status)))
       ((claim-info "c1" "If n is even, then n = 2k for some integer k" "conjectural")))

;; Query 3: Find all moves and their kind
!(test (collapse (match &mork (Move "even-sum-proof" $mid $state "open" $kind $summary)
                          (open-move $mid $kind $summary)))
       ((open-move "m1" "reduction" "Expand definition of even numbers")))

;; Query 4: Find all attempts and their workers
!(test (collapse (match &mork (Attempt "even-sum-proof" $aid $state $status $worker $summary)
                          (attempt-info $aid $status $worker $summary)))
       ((attempt-info "a1" "supported" "llm-explorer-1" "Expanded definition: n=2k, m=2j, so n+m=2(k+j)")))

;; Query 5: Find what claims support a state (via SUPPORTED_BY edges)
!(test (collapse (match &mork (Edge $eid SUPPORTED_BY $sid $cid)
                          (support-edge $eid $sid $cid)))
       ((support-edge "e1" "s1" "c1")))

;; Query 6: Find what moves are proposed by a state (via PROPOSES edges)
!(test (collapse (match &mork (Edge $eid PROPOSES $sid $mid)
                          (propose-edge $eid $sid $mid)))
       ((propose-edge "e2" "s1" "m1")))

;; Query 7: Find what state an attempt is on (via ON_STATE edges)
!(test (collapse (match &mork (Edge $eid ON_STATE $aid $sid)
                          (on-state-edge $eid $aid $sid)))
       ((on-state-edge "e3" "a1" "s1")))

;; Query 8: Find what move an attempt references (via ON_MOVE edges)
!(test (collapse (match &mork (Edge $eid ON_MOVE $aid $mid)
                          (on-move-edge $eid $aid $mid)))
       ((on-move-edge "e4" "a1" "m1")))

;; Query 9: Find supported attempts (completed work)
!(test (collapse (match &mork (Attempt "even-sum-proof" $aid $state "supported" $worker $summary)
                          (supported-attempt $aid $worker $summary)))
       ((supported-attempt "a1" "llm-explorer-1" "Expanded definition: n=2k, m=2j, so n+m=2(k+j)")))

