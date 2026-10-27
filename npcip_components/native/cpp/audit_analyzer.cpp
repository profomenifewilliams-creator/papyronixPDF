/* Offline JSONL audit summary. Does not execute, follow, or enrich input records. */
#include <fstream>
#include <iostream>
#include <map>
#include <regex>
#include <string>
int main(int argc,char**argv){
if(argc!=2){std::cerr<<"Usage: npc-audit-analyzer <audit.jsonl>\n";return 2;}
std::ifstream in(argv[1]);if(!in){std::cerr<<"Cannot open input file\n";return 1;}
std::regex action_re(R"("action"\s*:\s*"([^"]{1,120})")");
std::string line;std::map<std::string,unsigned long long> counts;unsigned long long lines=0,matched=0,malformed=0;
while(std::getline(in,line)){++lines;if(line.size()>1024*1024){++malformed;continue;}std::smatch m;if(std::regex_search(line,m,action_re)){++counts[m[1].str()];++matched;}else if(!line.empty())++malformed;}
if(in.bad()){std::cerr<<"Input read error\n";return 1;}
std::cout<<"lines="<<lines<<"\nrecords_with_action="<<matched<<"\nrecords_without_action_or_invalid="<<malformed<<"\nunique_actions="<<counts.size()<<"\n";
for(const auto&entry:counts)std::cout<<"action["<<entry.first<<"]="<<entry.second<<"\n";
std::cout<<"notice=offline summary only; output is not a finding of wrongdoing\n";return 0;
}
