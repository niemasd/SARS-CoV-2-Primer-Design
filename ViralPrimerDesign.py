#! /usr/bin/env python3
'''
Pipeline for designing primers from a collection of viral sequences
'''
VERSION = '0.0.1'

# imports
from gzip import open as gopen
from math import log2
from os import mkdir
from os.path import abspath, expanduser, isdir, isfile
from sys import argv, stdin, stderr
import argparse

# constants
DEFAULT_BUFSIZE = 1048576 # 1 MB
MAX_ENTROPY = 2
NUCS = {'A', 'C', 'G', 'T'}
NUM_SEQS_PROGRESS = 500

# helper class for logging
class Log:
    def __init__(self, loggern, quiet=False):
        self.log_f = open(loggern, 'w')
        if quiet:
            self.ostream = None
        else:
            self.ostream = stderr
    def __del__(self):
        self.log_f.close()
    def write(self, s):
        self.log_f.write(s)
        if self.ostream is not None:
            self.ostream.write(s)
        self.flush()
    def flush(self):
        self.log_f.flush()
        if self.ostream is not None:
            self.ostream.flush()

# parse user args
def parse_args():
    # check for -v/--version
    if '-v' in argv or '--version' in argv:
        print("ViralPrimerDesign v%s" % VERSION); exit(0)

    # use argparse to parse user arguments
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--sequences', required=False, type=str, default='stdin', help="Input Sequences (FASTA format)")
    parser.add_argument('-o', '--outdir', required=True, type=str, help="Output Directory")
    parser.add_argument('--skip_alignment', action="store_true", help="Skip Alignment (if input FASTA is already aligned)")
    parser.add_argument('-q', '--quiet', action="store_true", help="Quiet (hide verbose messages)")
    parser.add_argument('-v', '--version', action="store_true", help="Show Version Number")
    args = parser.parse_args()

    # check user arguments for validity
    if args.sequences != 'stdin' and not isfile(args.sequences):
        raise ValueError("File not found: %s" % args.sequences)
    args.outdir = abspath(expanduser(args.outdir))
    if isdir(args.outdir) or isfile(args.outdir):
        raise ValueError("Output exists: %s" % args.outdir)
    return args

# iterate over sequences of FASTA
def iter_fasta(in_fn):
    if in_fn == 'stdin':
        in_f = stdin
    elif in_fn.lower().endswith('.gz'):
        in_f = gopen(in_fn, 'rt')
    else:
        in_f = open(in_fn, 'r', buffering=DEFAULT_BUFSIZE)
    seq = None
    for line in in_f:
        l = line.strip()
        if len(l) == 0:
            continue
        if l.startswith('>'):
            if seq is not None:
                yield seq
            seq = ''
        else:
            seq += l.upper()
    in_f.close()

# count bases at each position of MSA
def count_bases(in_fn, logger=None):
    if logger is not None:
        logger.write("Counting bases from: %s\n" % in_fn)
    counts = None # counts[pos][nuc] = count
    for seq_ind, seq in enumerate(iter_fasta(in_fn)):
        if counts is None:
            counts = [dict() for _ in range(len(seq))]
        elif len(seq) != len(counts):
            raise ValueError("MSA sequences have differing lengths: %s" % in_fn)
        for i, c in enumerate(seq):
            if c not in NUCS:
                continue
            if c not in counts[i]:
                counts[i][c] = 0
            counts[i][c] += 1
        if logger is not None and (seq_ind+1) % NUM_SEQS_PROGRESS == 0:
            logger.write("Parsed %d sequences...\n" % (seq_ind+1))
    return counts

# write base counts
def write_counts(counts, out_fn, delim='\t', logger=None):
    if isfile(out_fn):
        raise ValueError("File exists: %s" % out_fn)
    if logger is not None:
        logger.write("Writing base counts to file...\n")
    out_f = open(out_fn, 'w'); NUCS_SORT = sorted(NUCS); out_f.write('Position (0-indexed)%s%s\n' % (delim, delim.join(NUCS_SORT)))
    for i, curr in enumerate(counts):
        out_f.write('%d%s%s\n' % (i, delim, delim.join(str(curr[c]) if c in curr else '0' for c in NUCS_SORT)))
    out_f.close()
    if logger is not None:
        logger.write("Base counts written to: %s\n" % out_fn)

# compute Shannon entorpy from MSA base counts
def compute_entropies(counts, logger=None):
    if logger is not None:
        logger.write("Computing Shannon entropies...\n")
    ents = [MAX_ENTROPY for _ in range(len(counts))] # ents[pos] = (max base freq, entropy)
    for i, curr in enumerate(counts):
        ent = MAX_ENTROPY
        if len(curr) != 0:
            ent = 0; tot = sum(curr.values()); m = max(curr.values())/tot
            for c in curr:
                p = curr[c]/tot
                ent -= (p*log2(p))
            ents[i] = ent
    return ents

# write Shannon entropies
def write_entropies(ents, out_fn, delim='\t', logger=None):
    if isfile(out_fn):
        raise ValueError("File exists: %s" % out_fn)
    if logger is not None:
        logger.write("Writing entropies to file...\n")
    out_f = open(out_fn, 'w'); out_f.write('Position (0-indexed)%sEntropy\n' % delim)
    for i, curr in enumerate(ents):
        out_f.write('%d%s%s\n' % (i, delim, curr))
    out_f.close()
    if logger is not None:
        logger.write("Entropies written to: %s\n" % out_fn)

# main program
if __name__ == "__main__":
    args = parse_args(); mkdir(args.outdir); logger = Log('%s/log.txt' % args.outdir, quiet=args.quiet)
    logger.write("=== ViralPrimerDesign v%s ===\n" % VERSION)
    logger.write("Command: %s\n" % ' '.join(argv))
    if not args.skip_alignment:
        args.sequences = align_mafft(args.sequences, '%s/sequences.aln' % args.outdir, logger=logger)
    counts = count_bases(args.sequences, logger=logger)
    write_counts(counts, '%s/base_counts.tsv' % args.outdir, logger=logger)
    ents = compute_entropies(counts, logger=logger)
    write_entropies(ents, '%s/entropies.tsv' % args.outdir, logger=logger)
