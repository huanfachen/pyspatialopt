# -*- coding: UTF-8 -*-
import logging
import sys
import arcpy
import pulp
import csv
import sys
from pyspatialopt.analysis import arcpy_analysis
from pyspatialopt.models import utilities
from pyspatialopt.models import covering
import os

def generate_binary_coverage_from_dist_matrix(list_dict_facility_demand_distance, dist_threshold, dl_id_field="demand_id", fl_id_field="facility_id", demand_field="demand", distance_field="distance", fl_variable_name=None):
    """
    Generates a dictionary representing the binary coverage of a facility to demand points
    :param list_dict_facility_demand_distance: (string) A dictionary containing pairwise distance and demand
    :param dist_threshold：(numeric) The distance threshold
    :param dl_id_field: (string) The name of the demand point id field in the list_dict_facility_demand_distance object
    :param fl_id_field: (string) The name of the facility id field in the list_dict_facility_demand_distance object AND fl
    :param demand_field: (string) The name of demand weight field in the list_dict_facility_demand_distance object
    :param distance_field: (string) The name of distance in metres field in the list_dict_facility_demand_distance object
    :param fl_variable_name: (string) The name to use to represent the facility variable
    :return: (dictionary) A nested dictionary storing the coverage relationships
    """
    # need to review the codes
    # Check parameters so we get useful exceptions and messages

    if fl_variable_name is None:
        fl_variable_name = "facility"

    logging.getLogger().info("Initializing facilities in output...")
    
    output = {
        # "version": version.__version__,
        "version": "1",
        "type": {
            "mode": "coverage",
            "type": "binary",
        },
        "demand": {},
        "totalDemand": 0.0,
        "totalServiceableDemand": 0.0,
        "facilities": {fl_variable_name: []}
    }

    set_facility_id = set()
    set_demand_id = set()
    for row in list_dict_facility_demand_distance:
        set_facility_id.add(str(row[fl_id_field]))
        # test if this demand id is contained
        new_demand_id = str(row[dl_id_field])
        if not new_demand_id in set_demand_id:
            output["demand"][new_demand_id] = {
                "area": 0,
                "demand": float(row[demand_field]),
                "serviceableDemand": 0.0,
                "coverage": {fl_variable_name: {}}
            }
            set_demand_id.add(new_demand_id)
        
    # add facility IDs to facilities
    for facility_id in set_facility_id:
        output["facilities"][fl_variable_name].append(facility_id)

    logging.getLogger().info("Determining binary coverage for each demand unit...")
    # logic: iterate over the data frame. If the demand id is not in the output, add an empty item. Then, check out if the facility covers the demand. If so, add to the list of coverage.
    # for each demand unit
    for row in list_dict_facility_demand_distance:
        # row: [dl_id_field, fl_id_field, distance, demand_field]

        if float(row[distance_field]) <= dist_threshold:
            output["demand"][str(row[dl_id_field])]["serviceableDemand"] = \
                output["demand"][str(row[dl_id_field])]["demand"]
            output["demand"][str(row[dl_id_field])]["coverage"][fl_variable_name][str(row[fl_id_field])] = 1

    # summary
    for row in output["demand"].values():
        output["totalServiceableDemand"] += row["serviceableDemand"]
        output["totalDemand"] += row["demand"]    
    logging.getLogger().info("Binary coverage successfully generated.")
    return output

def binary_mclp_distance_matrix(file_distance_matrix, service_dist, num_facility, list_field_req = ["facility_id", "demand_id", "demand", "distance"], facility_variable_name = "facility", workspace_path = "."):
    """
    Solve a binary and point-based MCLP based on a distance matrix
    :param file_distance_matrix: (string) file name of a distance matrix. CSV format.
    :param service_dist: (numeric) maximum service distance
    :param num_facility: (integer) number of facilities to locate
    :param list_field_req: (list of string) a list of fields in the file_distance_matrix
    :param facility_variable_name: (string) facility variable name in the coverage object
    :param workspace_path: (string) the folder path of file_distance_matrix
    :return: (dictionary) A dictionary storing the coverage result
    """
    # read the distance matrix
    with open(os.path.join(workspace_path, file_distance_matrix)) as csvfile:
        dict_pairwise_distance = [{k: v for k, v in row.items()}
        for row in csv.DictReader(csvfile, skipinitialspace=True)]

    # test if it contains the required field
    item_pairwise_distance = dict_pairwise_distance[1]
    
    for field in list_field_req:
        if field not in item_pairwise_distance.keys():
            print("Error: this field {} not found in the distance csv".format(field))
            sys.exit(0)

    # creat a coverage object. Need to write a new function
    dict_coverage = generate_binary_coverage_from_dist_matrix(list_dict_facility_demand_distance = dict_pairwise_distance, dl_id_field = "demand_id", fl_id_field = "facility_id", dist_threshold = service_dist, demand_field="demand", distance_field="distance", fl_variable_name=facility_variable_name)        
    
    # formulate model
    # logger.info("Creating MCLP model...")
    mclp = covering.create_mclp_model(dict_coverage, {"total": num_facility})

    # solve
    # logger.info("Solving MCLP...")
    mclp.solve(pulp.GLPK())

    # Get the unique ids of the facilities chosen

    # print elements of mclp
    # for var in mclp.variables():
    #     logger.info(var.name)

    # Get the id set of facilities chosen
    set_facility_id_chosen = set(utilities.get_ids(mclp, facility_variable_name))
    
    # logger.info("Set of facility ids: {}".format(set_facility_id_chosen))
    # logger.info("Number of facilities selected: {}".format(len(set_facility_id_chosen)))

    # Query the demand covered from the dict_coverage
    total_demand_covered = 0.0

    for demand_id, demand_obj in dict_coverage["demand"].items():
        # if this demand_id is covered by any facility in ids
        if not set_facility_id_chosen.isdisjoint(demand_obj["coverage"]["facility"].keys()):
            total_demand_covered += demand_obj["demand"]
        # for facility_id in ids:
        #     if facility_id in dict_coverage["demand"][demand_id]["coverage"]["facility"]:
        #         total_demand_covered += dict_coverage["demand"][demand_id]["demand"]
        #         break
    
    result_coverage = {"number_facility": num_facility,
    "number_facility_chosen": len(set_facility_id_chosen),
    "set_facility_id_chosen": set_facility_id_chosen,
    "total_demand": dict_coverage["totalDemand"], 
    "percent_demand_coverage":(100 * total_demand_covered) / dict_coverage["totalDemand"]
    }
    return result_coverage
    # logger.info("{0:.2f}% of demand is covered".format((100 * total_demand_covered) / dict_coverage["totalDemand"]))

if __name__ == "__main__":
    # Initialize a logger so we get formatted output
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = formatter = logging.Formatter('%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
    # setup stream handler to console output
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    import os
    scriptDir = os.path.dirname(os.path.realpath(__file__))

    # a distance matrix file (format of csv).
    # should contain the following fields: facility_id, demand_id, demand, distance
    workspace_path = r"."
    file_distance_matrix = r'SF_network_distance_candidateStore_16_censusTract_205_new.csv'

    service_dist=5000
    num_facility=5

    list_field_req = ["facility_id", "demand_id", "demand", "distance"]

    # do not change this variable unless you understand what it is 
    facility_variable_name = "facility"
    # read the distance matrix
    with open(os.path.join(workspace_path, file_distance_matrix)) as csvfile:
        dict_pairwise_distance = [{k: v for k, v in row.items()}
        for row in csv.DictReader(csvfile, skipinitialspace=True)]

    # test if it contains the required field
    item_pairwise_distance = dict_pairwise_distance[1]
    
    for field in list_field_req:
        if field not in item_pairwise_distance.keys():
            logger.info("Error: this field {} not found in the distance csv".format(field))
            sys.exit(0)
    logger.info(dict_pairwise_distance[1])

    # creat a coverage object. Need to write a new function
    dict_coverage = generate_binary_coverage_from_dist_matrix(list_dict_facility_demand_distance = dict_pairwise_distance, dl_id_field = "demand_id", fl_id_field = "facility_id", dist_threshold = service_dist, demand_field="demand", distance_field="distance", fl_variable_name=facility_variable_name)        
    
    # formulate model
    logger.info("Creating MCLP model...")
    mclp = covering.create_mclp_model(dict_coverage, {"total": num_facility})

    # solve
    logger.info("Solving MCLP...")
    mclp.solve(pulp.GLPK())

    #########################################
    # Not completed
    # reference: N:\SpOpt\PySpatialOpt_code\pso_mclp_lscp_wrapper.py mclp_solver_coverage_dict()

    # Get the unique ids of the facilities chosen
    logger.info("Extracting results")

    # print elements of mclp
    # for var in mclp.variables():
    #     logger.info(var.name)

    # Get the id set of facilities chosen
    set_facility_id_chosen = set(utilities.get_ids(mclp, facility_variable_name))
    
    logger.info("Set of facility ids: {}".format(set_facility_id_chosen))
    logger.info("Number of facilities selected: {}".format(len(set_facility_id_chosen)))

    # Query the demand covered from the dict_coverage
    total_demand_covered = 0.0

    for demand_id, demand_obj in dict_coverage["demand"].items():
        # if this demand_id is covered by any facility in ids
        if not set_facility_id_chosen.isdisjoint(demand_obj["coverage"]["facility"].keys()):
            total_demand_covered += demand_obj["demand"]
        # for facility_id in ids:
        #     if facility_id in dict_coverage["demand"][demand_id]["coverage"]["facility"]:
        #         total_demand_covered += dict_coverage["demand"][demand_id]["demand"]
        #         break

    logger.info("{0:.2f}% of demand is covered".format((100 * total_demand_covered) / dict_coverage["totalDemand"]))

    # use the binary_mclp_distance_matrix function
    result_coverage = binary_mclp_distance_matrix(file_distance_matrix = file_distance_matrix, service_dist = service_dist, num_facility = num_facility)
    logger.info(result_coverage)

    # test using a simple case
    # file_distance_matrix = "simple_case_distance_matrix.csv"
    # service_dist = 10
    # dict_num_facility_coverage = {1:5.0/15, 2:9.0/15, 3:12.0/15, 4:14.0/15, 5:15.0/15}
    # for num_facility, coverage in dict_num_facility_coverage:
    #     result_coverage = binary_mclp_distance_matrix(file_distance_matrix = file_distance_matrix, service_dist = service_dist, num_facility = num_facility)
        
