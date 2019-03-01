#!/usr/bin/env python3
"""
EMBL writer for ENA data submission. This implementation is basically just the
documentation at ftp://ftp.ebi.ac.uk/pub/databases/embl/doc/usrman.txt in
python form.

GFF convertion is based on specifications from:
https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md
"""

import sys
import time
import gzip
import logging
from concurrent.futures import ThreadPoolExecutor
from Bio import SeqIO
from BCBio import GFF

from gffemblconverter.feature_table.embl_writer import EmblWriter
from gffemblconverter.concise_log import ConciseStreamHandler

SHAMELESS_PLUG = """
###############################################################################
# NBIS 2018 - Sweden                                                          #
# Authors: Martin Norling, Niclas Jareborg, Jacques Dainat                    #
# Please visit https://github.com/NBISweden/EMBLmyGFF3 for more information.  #
###############################################################################

"""

def gff_input(args):
    """Convenience functions that opens the files supplied in the args
    structure in the appropriate way and returns them so that they can be
    supplied directly to a FeatureTable.
    """
    if args.gff_file.endswith(".gz"):
        infile = gzip.open(args.gff_file)
    else:
        infile = open(args.gff_file)

    if args.fasta.endswith(".gz"):
        infasta = gzip.open(args.fasta)
    else:
        infasta = open(args.fasta)

    seq_dict = SeqIO.to_dict(SeqIO.parse(infasta, "fasta"))

    return {"gff_files":infile, "base_dict":seq_dict}

def resolve_output(args):
    """Convenience function that returns either stdout or a file handle with
    the correct extension, depending on wheather it should be gzip'ed or not.
    """
    outfile = args.output
    if args.gzip:
        if not outfile.endswith(".embl.gz"):
            outfile += ".gz" if outfile.endswith(".embl") else ".embl.gz"
        return gzip.open(outfile, "wb")
    if not outfile.endswith(".embl"):
        outfile += ".embl"
    return open(outfile, "wb")

if __name__ == '__main__':

    import argparse

    PARSER = argparse.ArgumentParser(description=__doc__)

    # Positional arguments
    PARSER.add_argument("gff_file", help="Input gff-file.")
    PARSER.add_argument("fasta", help="Input fasta sequence.")

    # Feature table header information
    HEADER = PARSER.add_argument_group("header information")

    HEADER.add_argument("--accession",
                        default="XXX",
                        help=("Accession number(s) for the entry. This value"
                              " is automatically generated by ENA during the"
                              " submission process."))

    HEADER.add_argument("--classification",
                        help=("Organism classification e.g 'Eukaryota;"
                              " Opisthokonta; Metazoa;'. If not set, will be"
                              " retrieved online on the NCBI taxonomy DB based"
                              " on the species name or taxid."))

    HEADER.add_argument("--created",
                        help=("Creation time of the original entry, formatted"
                              " as: 'YYYY-MM-DD' or 'DD-MON-YYYY'."))

    HEADER.add_argument("--data_class",
                        default="XXX",
                        help="Data class of the sample.",
                        choices=["CON", "PAT", "EST", "GSS", "HTC", "HTG",
                                 "MGA", "WGS", "TSA", "STS", "STD"])

    HEADER.add_argument("--description",
                        default=["XXX"],
                        nargs="+",
                        help="Short description of the data.")

    HEADER.add_argument("--keywords",
                        default=[],
                        nargs="+",
                        help="Keywords for the entry.")

    HEADER.add_argument("--locus_tag",
                        help=("Locus tag prefix used to set the locus_tag"
                              " qualifier. The locus tag has to be registered"
                              " at ENA prior to submission"))

    HEADER.add_argument("--molecule_type",
                        help="Molecule type of the sample.",
                        choices=["genomic DNA", "genomic RNA", "mRNA", "tRNA",
                                 "rRNA", "other RNA", "other DNA",
                                 "transcribed RNA", "viral cRNA",
                                 "unassigned DNA", "unassigned RNA"])

    HEADER.add_argument("--organelle",
                        help=("Sample organelle, ex. 'Mitochondrion', 'Plasmid"
                              " pBR322', or 'Plastid:Chloroplast'."))

    HEADER.add_argument("--project_id",
                        default="XXX",
                        help=("The International Nucleotide Sequence Database"
                              " Collaboration (INSDC) Project Identifier that"
                              " has been assigned to the entry."))

    PARSER.add_argument("--reference_comment",
                        default=None,
                        help="Reference Comment.")

    HEADER.add_argument("--reference_group",
                        default="XXX",
                        help=("Reference Group, the working groups/consortia"
                              " that produced the record."))

    PARSER.add_argument("--reference_xref",
                        default=None,
                        help="Reference cross-reference.")

    PARSER.add_argument("--reference_author", "--author",
                        nargs="+",
                        default="",
                        help="Author for the reference.")

    PARSER.add_argument("--reference_title",
                        help="Reference Title.")

    PARSER.add_argument("--reference_publisher",
                        default=None,
                        help="Reference publishing location.")

    PARSER.add_argument("--reference_position",
                        nargs="+",
                        default=[],
                        help="Sequence position described by the reference.")

    HEADER.add_argument("--species",
                        help=("Submission species, formatted as 'Genus"
                              " species' or using a taxid."))

    HEADER.add_argument("--taxonomy",
                        help="Source taxonomy.",
                        default="XXX",
                        choices=["PHG", "ENV", "FUN", "HUM", "INV", "MAM",
                                 "VRT", "MUS", "PLN", "PRO", "ROD", "SYN",
                                 "TGN", "UNC", "VRL"])

    HEADER.add_argument("--topology",
                        help="Sequence topology.",
                        choices=["linear", "circular"])

    HEADER.add_argument("--translation_table",
                        type=int,
                        help="Translation table for the submission DNA.",
                        choices=list(range(1, 26)))

    HEADER.add_argument("--version",
                        type=int,
                        default=1,
                        help="Submission version number.")


    # Logging arguments
    LOGGING = PARSER.add_argument_group("logging control")
    LOGGING.add_argument("-v", "--verbose",
                         action="count",
                         default=2,
                         help="Increase logging verbosity.")
    LOGGING.add_argument("-q", "--quiet",
                         action="count",
                         default=0,
                         help="Decrease logging verbosity.")

    # Script behaviour arguments
    PARSER.add_argument("--shame",
                        action="store_true",
                        help="Suppress the shameless plug.")

    PARSER.add_argument("-t", "--num_threads",
                        type=int, default=1,
                        help="Number of threads to use for conversion")

    PARSER.add_argument("-o", "--output",
                        help="Output filename, default is stdout.")

    PARSER.add_argument("-z", "--gzip",
                        action="store_true",
                        help="Gzip output file")

    ARGS = PARSER.parse_args()

    LOGGER = logging.getLogger()
    HANDLER = ConciseStreamHandler()
    FORMATTER = logging.Formatter(("%(asctime)s %(levelname)s %(module)s: "
                                   "%(message)s"))
    HANDLER.setFormatter(FORMATTER)
    LOGGER.setLevel(50-10*(ARGS.verbose-ARGS.quiet))
    LOGGER.addHandler(HANDLER)

    RECORDS = []

    if not ARGS.shame:
        print(SHAMELESS_PLUG)

    THREAD_POOL = None
    if ARGS.num_threads > 1:
        THREAD_POOL = ThreadPoolExecutor(max_workers=ARGS.num_threads)

    logging.info("Starting record parsing")
    for i, record in enumerate(GFF.parse(**gff_input(ARGS))):
        RECORDS += [EmblWriter(record,
                               thread_pool=THREAD_POOL,
                               header=ARGS)]

    if ARGS.output:
        OUTFILE = resolve_output(ARGS)

    for i, record in enumerate(RECORDS):
        while record.get_progress() < 1.0:
            time.sleep(0.1)
        if ARGS.output:
            OUTFILE.write(f"{record}\n".encode('utf8'))
        else:
            sys.stdout.write(f"{record}\n")
        break
