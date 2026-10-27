/* C++ local file fingerprint CLI, using project's pure C SHA-256 header. */
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include "sha256.h"
static const char* detect_type(const unsigned char* b,size_t n){
if(n>=8&&std::memcmp(b,"\x89PNG\r\n\x1a\n",8)==0)return "PNG image";
if(n>=3&&b[0]==0xff&&b[1]==0xd8&&b[2]==0xff)return "JPEG image";
if(n>=4&&std::memcmp(b,"%PDF",4)==0)return "PDF document";
if(n>=4&&b[0]=='P'&&b[1]=='K'&&b[2]==3&&b[3]==4)return "ZIP container";
if(n>=2&&b[0]=='M'&&b[1]=='Z')return "Windows executable";
if(n>=4&&b[0]==0x7f&&std::memcmp(b+1,"ELF",3)==0)return "ELF executable";
return n==0?"Empty file":"Unknown / text / binary";
}
int main(int argc,char**argv){
if(argc!=2){std::cerr<<"Usage: npc-filehash-cpp <path>\n";return 2;}
std::ifstream in(argv[1],std::ios::binary);if(!in){std::cerr<<"Cannot open file\n";return 1;}
npcip_sha256_ctx ctx;npcip_sha256_init(&ctx);uint8_t buf[65536],first[16]{};size_t first_n=0;uint64_t size=0;
while(in){in.read(reinterpret_cast<char*>(buf),sizeof buf);const auto n=static_cast<size_t>(in.gcount());if(n){if(first_n<sizeof first){auto take=std::min(n,sizeof first-first_n);std::memcpy(first+first_n,buf,take);first_n+=take;}size+=n;npcip_sha256_update(&ctx,buf,n);}}
if(in.bad()){std::cerr<<"Read failed\n";return 1;}uint8_t hash[32];npcip_sha256_final(&ctx,hash);
std::cout<<"file="<<argv[1]<<"\nsize_bytes="<<size<<"\nkind="<<detect_type(first,first_n)<<"\nsha256=";
const char*hex="0123456789abcdef";for(auto x:hash)std::cout<<hex[x>>4]<<hex[x&15];
std::cout<<"\nnotice=local-only; content was not uploaded or changed\n";return 0;
}
