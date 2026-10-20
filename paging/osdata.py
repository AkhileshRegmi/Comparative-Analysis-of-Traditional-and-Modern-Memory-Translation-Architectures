"""OS study: which page-table technique each OS uses, why, and what it trades.

Each documented fact carries a URL and how well it was verified:
  "opened"     = the page was opened and the sentence read.
  "secondhand" = read on an opened page that quotes another source; the original was not opened.
  "snippet"    = seen only in a search-result summary; the page itself was not opened.
"inferred" lines are our reasoning, not a source.

"config" is what the simulator runs for the OS today. "page_alts" are the page sizes the OS could switch to
under its own organization; the "what if" analysis also runs every other organization at the current page size.
"hardware_org" is the organization the CPU's MMU walks; the OS cannot change it on its own.
"""
from .config import KB, MB

# Shared trade-offs of each organization (textbook reasoning, cross-checked against the sources below).
ORG_TRADEOFFS = {
    "multi-level": {
        "up": ["Table space is only allocated for the parts of the address space a program actually uses, so even a "
               "huge 64-bit address space needs only a small table.",
               "Entries for neighbouring pages sit next to each other, so a lookup often finds them already in the "
               "processor's data cache.",
               "Large pages fit in naturally: the lookup simply stops one or two levels earlier."],
        "down": ["Every TLB miss reads one entry per level: 4 memory reads on 4-level x86-64, 5 with 5-level paging.",
                 "Inside a virtual machine a miss can cost up to 24 memory reads, because both the guest's table and "
                 "the host's table have to be walked."],
    },
    "single-level": {
        "up": ["A TLB miss needs exactly one memory read: the page number is used directly as the position in the "
               "table."],
        "down": ["The table needs a slot for every possible page in the address space, used or not. For 64-bit "
                 "address spaces it is enormous, and every process needs its own copy."],
    },
    "hashed": {
        "up": ["When few pages collide, a TLB miss needs about one memory read, however large the address space is.",
               "The table only holds pages that are actually mapped, so its size follows the program's memory use, "
               "not the size of the address space."],
        "down": ["The hash spreads neighbouring pages across the table, so a lookup rarely finds its entry already in"
                 " the processor's data cache.",
                 "Large pages and mixed page sizes are harder to support, because the lookup must know the page size "
                 "before it can compute the hash.",
                 "Pages whose hashes collide are chained together, and each extra link costs another memory read; "
                 "computing the hash also costs time on every miss."],
    },
    "inverted": {
        "up": ["There is one table for the whole machine, sized by physical memory, no matter how many processes are "
               "running."],
        "down": ["A lookup reads the anchor table first and then searches a chain: in this simulator that is about "
                 "twice the reads of a hashed table.",
                 "Each physical frame has exactly one entry, so a frame shared by two processes (shared memory) "
                 "cannot easily be recorded for both of them."],
    },
}

FEASIBILITY = {
    "x86-64": "Hypothetical. On x86-64 the processor itself reads the page table and only understands a 4-level tree."
              " A different table type would need a new processor design, or a processor that hands TLB misses to the"
              " OS to resolve in software (a software-managed TLB).",
    "arm64": "Hypothetical. On Arm the processor itself reads the page table and only understands Arm's multi-level "
             "format. A different table type would need new hardware.",
    "power": "Real. The POWER9 processor can read both a radix tree and a hashed table; Linux chooses one when it "
             "boots (the disable_radix boot option selects the hashed table).",
    "power_other": "Hypothetical. The POWER9 processor can only read a radix tree or a hashed table; a single-level "
                   "or inverted table would need new hardware.",
}

OSES = [
    {
        "id": "windows",
        "name": "Windows x64",
        "cpu": "x86-64",
        "technique": "Multi-level table with 4 levels (the x86-64 format), 4 KB pages by default; 2 MB pages only "
                     "when a program asks for them",
        "config": {"org": "multi-level", "page_size": 4 * KB},
        "hardware_org": "multi-level",
        "page_alts": [("2 MB large pages", 2 * MB)],
        "config_note": "4 KB, radix, 48-bit VA is a modelling assumption matched to x86-64 hardware (4-level, 48-bit: "
                       "see Linux x86-64). No opened Microsoft page states the default page size for x64.",
        "why": ["On x86-64, the processor itself reads the page table on every TLB miss, and it only understands a "
                "4-level tree. Windows therefore has to build its page table in exactly that format.",
                "4 KB pages let Windows hand out, track and swap memory in small pieces, which suits thousands of "
                "ordinary desktop processes that each use little memory.",
                "2 MB pages are opt-in because Windows can never swap them out to disk and must find 2 MB of "
                "contiguous free physical memory for each one."],
        "up": ["Little memory is wasted: each allocation is rounded up by at most 4 KB minus one byte.",
               "Each 4 KB page can be swapped to disk on its own, so memory a program is not using can be given to "
               "other programs.",
               "Programs that use a lot of memory, such as databases and games, can still request 2 MB pages."],
        "down": ["Each TLB entry covers only 4 KB, so a 64-entry TLB (the size used in this simulator) covers just "
                 "256 KB of memory. Programs that use more than that miss the TLB often, and every miss costs 4 "
                 "memory reads, one per level of the tree.",
                 "To use 2 MB pages a program needs a special privilege (SeLockMemoryPrivilege), and the request can "
                 "fail when physical memory has become fragmented after a long uptime."],
        "documented": [
            {"text": "Windows debugger documentation walks an address through a page directory entry (PDE) and a page "
                     "table entry (PTE), with a per-process directory base (DirBase).",
             "url": "https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/converting-virtual-addresses-to-physical-addresses",
             "verified": "opened"},
            {"text": "Large pages need SeLockMemoryPrivilege and VirtualAlloc with MEM_LARGE_PAGES; size and alignment "
                     "must be a multiple of the large-page minimum.",
             "url": "https://learn.microsoft.com/en-us/windows/win32/memory/large-page-support", "verified": "opened"},
            {"text": "Large-page memory is nonpageable (always resident); each large page needs contiguous physical "
                     "memory, which may be hard to get after long uptime.",
             "url": "https://learn.microsoft.com/en-us/windows/win32/memory/large-page-support", "verified": "opened"},
            {"text": "GetLargePageMinimum: the minimum large-page size \"varies, but it is typically 2 MB or greater\".",
             "url": "https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-getlargepageminimum",
             "verified": "opened"},
        ],
        "inferred": ["Making large pages the default would remove paging flexibility and fail on fragmented machines."],
    },
    {
        "id": "linux-x86",
        "name": "Linux x86-64",
        "cpu": "x86-64",
        "technique": "4-level radix tree (5-level optional), 4 KB pages; transparent huge pages (2 MB)",
        "config": {"org": "multi-level", "page_size": 4 * KB},
        "hardware_org": "multi-level",
        "page_alts": [("2 MB huge pages", 2 * MB)],
        "config_note": "4 KB with 48-bit VA (4 levels) is the base configuration.",
        "why": ["The CPU dictates the radix layout; Linux's own generic page tables are also a radix tree.",
                "A 4 KB base keeps waste low; transparent huge pages add reach automatically where it pays.",
                "5-level paging exists for machines that need more than 256 TiB of virtual space."],
        "up": ["Huge pages without application changes (THP), switchable per system or per region.",
               "One page-table design shared across many architectures inside the kernel."],
        "down": ["THP can add latency spikes and memory bloat, which is why it can be limited to madvise or disabled.",
                 "5-level paging adds a fifth read to every miss."],
        "documented": [
            {"text": "THP can be disabled, enabled only inside MADV_HUGEPAGE regions, or enabled system wide.",
             "url": "https://www.kernel.org/doc/html/latest/admin-guide/mm/transhuge.html", "verified": "opened"},
            {"text": "The THP page's examples assume a 4K base page and 2M huge page, and note the numbers vary by CPU "
                     "architecture.",
             "url": "https://www.kernel.org/doc/html/latest/admin-guide/mm/transhuge.html", "verified": "opened"},
            {"text": "4-level paging: 256 TiB virtual and 64 TiB physical. 5-level paging: 128 PiB virtual and 4 PiB "
                     "physical.",
             "url": "https://www.kernel.org/doc/html/latest/arch/x86/x86_64/5level-paging.html", "verified": "opened"},
            {"text": "x86-64 radix page tables cost four memory references per TLB miss, 24 when virtualized, which can "
                     "account for 5% to 90% of runtime (Yaniv and Tsafrir, SIGMETRICS 2016).",
             "url": "https://doi.org/10.1145/2896377.2901456", "verified": "snippet"},
        ],
        "inferred": ["The THP latency-spike downside is common operational knowledge, not from an opened source."],
    },
    {
        "id": "macos",
        "name": "macOS, Apple Silicon",
        "cpu": "arm64",
        "technique": "Multi-level table in the Arm format, with 16 KB pages",
        "config": {"org": "multi-level", "page_size": 16 * KB},
        "hardware_org": "multi-level",
        "page_alts": [("4 KB pages (as Rosetta processes see)", 4 * KB)],
        "config_note": "16 KB granule from the sources below. Radix and 48-bit VA are modelling assumptions: no opened "
                       "source states them for Apple silicon.",
        "why": ["On Arm, the processor itself reads the page table on every TLB miss, and it only understands Arm's "
                "multi-level format. macOS therefore has to build its page table in that format.",
                "Arm processors let the OS choose the page size. Apple makes both the chips and the OS, so it could "
                "choose 16 KB without staying compatible with other vendors' hardware.",
                "With 16 KB pages each TLB entry covers four times as much memory as with 4 KB pages, so the same TLB"
                " covers four times as much memory."],
        "up": ["Fewer TLB misses and fewer page faults for the same amount of memory, because each translation covers"
               " more of it.",
               "Intel programs running under Rosetta (Apple's translation layer) still see 4 KB pages, so they keep "
               "working unchanged."],
        "down": ["More memory is wasted per allocation: each request is rounded up to the next 16 KB, so up to 16 KB "
                 "minus one byte can be lost every time.",
                 "Programs that assumed 4 KB pages had to be fixed when Macs moved from Intel to Apple Silicon."],
        "documented": [
            {"text": "Apple's WWDC20 session says page size is one of the differences between Intel and Apple Silicon "
                     "Mac processes.",
             "url": "https://developer.apple.com/videos/play/wwdc2020/10686/", "verified": "opened"},
            {"text": "For applications running in Rosetta, \"everything matches behavior on an Intel-based Mac\".",
             "url": "https://developer.apple.com/videos/play/wwdc2020/10686/", "verified": "opened"},
            {"text": "Numeric values (Intel 4 kB, Apple Silicon 16 kB; Rosetta gets 4 KB) appear in community notes on "
                     "WWDC20 session 10214; seen in a search-result summary only.",
             "url": "https://wwdcnotes.com/notes/wwdc20/10214", "verified": "snippet"},
        ],
        "inferred": ["A 16 KB base is a reach-oriented choice that a vertically integrated platform can afford."],
    },
    {
        "id": "android",
        "name": "Android (ARM64)",
        "cpu": "arm64",
        "technique": "Multi-level translation tables, 4 KB pages; 16 KB supported from Android 15",
        "config": {"org": "multi-level", "page_size": 4 * KB},
        "hardware_org": "multi-level",
        "page_alts": [("16 KB pages", 16 * KB)],
        "config_note": "Row shows the historic 4 KB default. 48-bit VA and radix are modelling assumptions.",
        "why": ["Inherited 4 KB from Linux and the app ecosystem; native libraries were built assuming 4 KB.",
                "Google is moving to 16 KB because it measured faster launches and boot."],
        "up": ["4 KB: lowest memory use, which matters on phones with little RAM.",
               "16 KB: faster app launch, camera start and boot (Google's figures)."],
        "down": ["4 KB: less TLB reach, more page faults.",
                 "16 KB: slightly more memory used, and every native library must be rebuilt 16 KB-aligned."],
        "documented": [
            {"text": "\"Historically, Android has only supported 4 KB memory page sizes.\"",
             "url": "https://developer.android.com/guide/practices/page-sizes", "verified": "opened"},
            {"text": "\"Beginning with Android 15, AOSP supports devices that are configured to use a page size of "
                     "16 KB.\"",
             "url": "https://developer.android.com/guide/practices/page-sizes", "verified": "opened"},
            {"text": "Google's numbers: app launch under memory pressure 3.16% lower on average (up to 30% for some "
                     "apps); power draw during launch down 4.56%; camera hot start 4.48% faster, cold start 6.60% "
                     "faster; boot 8% (about 950 ms) faster.",
             "url": "https://developer.android.com/guide/practices/page-sizes", "verified": "opened"},
            {"text": "16 KB devices \"use slightly more memory on average\". No figure is given.",
             "url": "https://developer.android.com/guide/practices/page-sizes", "verified": "opened"},
        ],
        "inferred": ["Why Android waited until Android 15 is not stated in the source; app compatibility is our guess."],
    },
    {
        "id": "linux-arm64",
        "name": "Linux ARM64 (servers)",
        "cpu": "arm64",
        "technique": "Multi-level table in the Arm format; the page size (4 KB or 64 KB) is fixed when the Linux "
                     "kernel is built",
        "config": {"org": "multi-level", "page_size": 4 * KB},
        "hardware_org": "multi-level",
        "page_alts": [("64 KB pages", 64 * KB)],
        "config_note": "Runs the 4 KB / 48-bit configuration. The 64 KB alternative is documented with 2 levels at "
                       "42-bit VA; here it is run at 48-bit VA (3 levels).",
        "why": ["On Arm, the processor itself reads the page table on every TLB miss, and it only understands Arm's "
                "multi-level format. Linux therefore has to build its page table in that format.",
                "Arm processors support 4 KB, 16 KB and 64 KB pages. Each Linux distribution picks one page size when"
                " it builds (compiles) its kernel, and every program on that machine then uses it.",
                "64 KB pages suit servers with a lot of memory; 4 KB pages suit general-purpose machines and software"
                " that assumes 4 KB."],
        "up": ["With 64 KB pages the tree needs fewer levels (2 instead of 3 or 4, according to the kernel "
               "documentation), so a TLB miss costs fewer memory reads.",
               "With 64 KB pages each TLB entry covers 16 times as much memory as with 4 KB pages, so programs that "
               "use a lot of memory miss the TLB far less often."],
        "down": ["With 64 KB pages each allocation is rounded up to the next 64 KB, so up to 64 KB minus one byte can"
                 " be wasted every time; small files and small processes cost more memory.",
                 "The page size is fixed when the kernel is built: changing it means installing a different kernel, "
                 "and it applies to every program on the machine, not to one program at a time."],
        "documented": [
            {"text": "4 KB pages: 3 or 4 translation levels, 39-bit (512 GB) or 48-bit (256 TB) VA.",
             "url": "https://docs.kernel.org/arch/arm64/memory.html", "verified": "opened"},
            {"text": "64 KB pages: 2 levels, 42-bit (4 TB) VA; optional 52-bit VA only with 64 KB pages.",
             "url": "https://docs.kernel.org/arch/arm64/memory.html", "verified": "opened"},
        ],
        "inferred": ["A build-time choice lets each product pick its trade-off: 4 KB for low waste, 64 KB for reach."],
    },
    {
        "id": "linux-power",
        "name": "Linux on IBM POWER9",
        "cpu": "power",
        "technique": "Multi-level (radix) table with 64 KB pages by default; Linux can instead boot with a hashed "
                     "page table",
        "config": {"org": "multi-level", "page_size": 64 * KB},
        "hardware_org": "multi-level or hashed",
        "page_alts": [("4 KB pages", 4 * KB)],
        "config_note": "64 KB radix from the TU Berlin POWER9 guide. Our radix model uses 3 levels at 64 KB on a 48-bit "
                       "VA; real POWER9 radix differs. Hash mode is modelled by our chained hashed table, which is a "
                       "simplification of POWER's hashed page table.",
        "why": ["Older POWER processors only understood a hashed page table. POWER9 added support for a radix tree, "
                "which the processor can read directly from the page tables Linux already keeps for itself.",
                "A radix tree works better for programs that access nearby addresses together; a hashed table suits "
                "programs whose memory is huge and scattered."],
        "up": ["Radix: entries for neighbouring pages sit next to each other in memory, so a lookup often finds them "
               "already in the processor's data cache instead of going out to RAM.",
               "Radix: Linux keeps a single set of page tables. In hashed mode it must also maintain a separate "
               "hashed table, used only by the hardware, that holds a second copy of every translation.",
               "Hashed: a translation can be found with at most about two memory reads."],
        "down": ["Radix: when nothing is in the cache, a lookup needs more memory reads than a hashed lookup, one per"
                 " level of the tree.",
                 "Hashed: entries are scattered across the table, so each one tends to sit in a different block of "
                 "memory; most TLB misses therefore have to read from RAM rather than from the processor's cache."],
        "documented": [
            {"text": "\"Traditionally Power server machines have used the Hashed Page Table MMU mode.\" \"Power ISA 3.0 "
                     "defines a new MMU mode, known as Radix Tree Translation, where the hardware can directly operate "
                     "on the Linux page tables.\"",
             "url": "https://android-kvm.googlesource.com/linux/+/ee3caed37d763ab28f8ac55563f38fb7530c6252%5E",
             "verified": "opened"},
            {"text": "Linux stores its page tables big-endian \"even in hash mode where they are not actually used by "
                     "the hardware\".",
             "url": "https://android-kvm.googlesource.com/linux/+/ee3caed37d763ab28f8ac55563f38fb7530c6252%5E",
             "verified": "opened"},
            {"text": "\"Like on x86_64, page table is stored as a radix tree by default (radix MMU mode).\" POWER9 also "
                     "supports a hash MMU mode, enabled with disable_radix on the boot command line. 64 KB pages are "
                     "the default; hash mode uses 16 MB and 16 GB huge pages instead of 2 MB and 1 GB.",
             "url": "https://github.com/TU-Berlin-DIMA/fast-interconnects/blob/master/guides/power9.md",
             "verified": "opened"},
            {"text": "IBM: the HPT \"does not cache well\"; each PTE tends to go into a separate cache line, so most TLB "
                     "misses need main memory. Radix \"is expected to be more efficient than HPT translation for "
                     "workloads with high locality of references.\" (IBM POWER9 system software, IBM J. Res. Dev.)",
             "url": "https://forums.raptorcs.com/index.php/topic,589.0.html", "verified": "secondhand"},
        ],
        "inferred": ["POWER is the one mainstream platform where the OS really can switch organization, so it is the "
                     "real-world check on our hypothetical switches."],
    },
]

# Research on the hashed-versus-radix question that is not tied to one OS.
STUDIES = [
    {"text": "Yaniv and Tsafrir, \"Hash, Don't Cache (the Page Table)\", SIGMETRICS 2016: carefully optimized hashed "
             "page tables beat x86-64 radix tables with page-walk caches, shortening runtimes by 1% to 27% bare-metal "
             "and 6% to 32% virtualized, but make superpages harder to support.",
     "url": "https://doi.org/10.1145/2896377.2901456", "verified": "snippet"},
    {"text": "Wikipedia: inverted page tables are used on PowerPC, UltraSPARC and IA-64; the hash function gives poor "
             "cache locality.",
     "url": "https://en.wikipedia.org/wiki/Page_table", "verified": "opened"},
]

# Costs of each suggested change that the latency and table-memory numbers do not show. Facts come from the
# sources listed on each OS entry; "caveat" lines are limits of our model.
SWITCH_DRAWBACKS = {
    ("Windows x64", "2 MB large pages"): [
        "Needs the SeLockMemoryPrivilege privilege and a VirtualAlloc call with MEM_LARGE_PAGES.",
        "Large-page memory can never be swapped out to disk; it stays in RAM until the program frees it.",
        "Each large page needs contiguous physical memory, which may be hard to get after long uptime.",
        "Memory is handed out in whole 2 MB pages, so small allocations waste far more.",
    ],
    ("Linux ARM64 (servers)", "64 KB pages"): [
        "Each allocation is rounded up to the next 64 KB, so up to 64 KB minus one byte can be wasted every time; "
        "small files and small processes cost more memory.",
        "The page size is fixed when the kernel is built: changing it means installing a different kernel, and it "
        "applies to every program on the machine.",
    ],
    ("Linux on IBM POWER9", "switch to hashed"): [
        "IBM expects a radix tree to beat a hashed table for programs that access nearby addresses together "
        "(high locality). This simulator has no processor caches, so it cannot show that advantage.",
        "In hashed mode the entries are scattered, so each one tends to sit in a different block of memory and "
        "most TLB misses have to read from RAM rather than from the processor's cache.",
        "In hashed mode the large pages are 16 MB and 16 GB instead of 2 MB and 1 GB.",
    ],
}


def switch_drawbacks(os_name: str, option: str, organization: str) -> list[str]:
    """Costs of one what-if option: sourced notes if we have them, else the organization's general downsides."""
    if (os_name, option) in SWITCH_DRAWBACKS:
        return SWITCH_DRAWBACKS[os_name, option]
    if option.startswith("switch to"):
        return ORG_TRADEOFFS[organization]["down"]
    return next(o["down"] for o in OSES if o["name"] == os_name)


# The OSes the app compares: they differ in page size and in how much room the hardware leaves.
#   Windows x64: 4 KB base pages, with 2 MB large pages only on request.
#   Linux ARM64 servers: an Arm machine whose real alternative is 64 KB pages, fixed per kernel build.
#   Linux on POWER9: the one case where the page-table organization itself can be switched.
FEATURED = ("Windows x64", "Linux ARM64 (servers)", "Linux on IBM POWER9")
FEATURED_OSES = [o for o in OSES if o["name"] in FEATURED]


DROPPED = [
    ["AIX / POWER",
     "IBM's AIX page-size documentation lists 4 KB, 64 KB, 16 MB and 16 GB pages but never mentions which table "
     "AIX uses, so AIX itself is left out. Linux on POWER9 covers the hashed-versus-radix case instead."],
]
